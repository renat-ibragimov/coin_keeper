"""The cascade diamond: deleting a user with personal catalog items.

DELETE FROM users fires two cascades that meet at the user's own catalog items:

    users --CASCADE--> collection_items --+
      |                                   +--> catalog_items (created_by)
      +--CASCADE--> catalog_items --------+

PostgreSQL handles this: all referential actions of one statement go into the
same after-trigger queue, so the coins are gone by the time the check on
catalog_items runs. What these tests pin down is that the delete really does
succeed in one statement, leaves nothing orphaned, and does not touch the
shared catalog — and, separately, that the foreign key still refuses to leave a
coin without its catalog item.

See docs/02-data-model.md, the section on NO ACTION versus RESTRICT.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    CatalogItem,
    CollectionItem,
    Currency,
    Expense,
    MarketPriceSnapshot,
    MediaFile,
    User,
)
from app.models.enums import (
    CollectionGroup,
    ExpenseCategory,
    MediaRole,
    MediaSource,
    UserRole,
)
from tests.seed import country_by_code


async def _build_user_with_personal_items(session: AsyncSession) -> int:
    """A user owning personal catalog items plus coins sitting on them."""
    currency = Currency(code="UAH", name="Hryvnia", symbol="UAH")
    country = await country_by_code(session, "UA")
    session.add(currency)
    await session.flush()

    user = User(
        email="cascade-subject@example.com",
        password_hash="not-a-real-hash",
        role=UserRole.USER,
        is_active=True,
        email_verified=True,
    )
    session.add(user)
    await session.flush()

    # A shared record must survive the delete untouched.
    shared = CatalogItem(
        country_id=country.id,
        collection_group=CollectionGroup.CIRCULATION,
        title_original="Shared issue",
        issue_year=2020,
        created_by=None,
    )
    personal = CatalogItem(
        country_id=country.id,
        collection_group=CollectionGroup.COMMEMORATIVE,
        title_original="Personal issue",
        issue_year=2021,
        created_by=user.id,
    )
    session.add_all([shared, personal])
    await session.flush()

    # One coin on the personal item — this is what closes the diamond — and one
    # on the shared item.
    on_personal = CollectionItem(
        owner_id=user.id,
        catalog_item_id=personal.id,
        quantity=1,
        acquisition_date=date(2021, 5, 1),
        purchase_price=Decimal("150.00"),
        purchase_currency="UAH",
        purchase_rate_uah=Decimal("1.000000"),
    )
    on_shared = CollectionItem(owner_id=user.id, catalog_item_id=shared.id, quantity=2)
    session.add_all([on_personal, on_shared])
    await session.flush()

    session.add_all(
        [
            Expense(
                owner_id=user.id,
                category=ExpenseCategory.COIN_PURCHASE,
                amount=Decimal("150.00"),
                currency_code="UAH",
                expense_date=date(2021, 5, 1),
                catalog_item_id=personal.id,
                collection_item_id=on_personal.id,
            ),
            MediaFile(
                catalog_item_id=personal.id,
                owner_id=user.id,
                role=MediaRole.OBVERSE,
                source=MediaSource.USER_UPLOAD,
                storage_key="catalog/personal/obverse.webp",
            ),
            MarketPriceSnapshot(
                catalog_item_id=personal.id,
                source="Manual",
                price=Decimal("200.00"),
                currency_code="UAH",
                observed_at=datetime.now(UTC),
                created_by=user.id,
            ),
        ]
    )
    await session.flush()
    return int(user.id)


async def test_deleting_a_user_with_personal_items_leaves_nothing_orphaned(
    db_session: AsyncSession,
) -> None:
    user_id = await _build_user_with_personal_items(db_session)

    # A single statement, exactly as a delete from the application would run.
    # Both cascades resolve inside it.
    await db_session.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
    await db_session.flush()

    async def count(statement: object) -> int:
        result = await db_session.execute(statement)  # type: ignore[arg-type]
        return int(result.scalar_one())

    assert await count(select(func.count()).select_from(User).where(User.id == user_id)) == 0
    assert (
        await count(
            select(func.count())
            .select_from(CollectionItem)
            .where(CollectionItem.owner_id == user_id)
        )
        == 0
    )
    # Personal catalog items go with their author...
    assert (
        await count(
            select(func.count()).select_from(CatalogItem).where(CatalogItem.created_by == user_id)
        )
        == 0
    )
    # ...and the shared catalog is untouched.
    assert (
        await count(
            select(func.count()).select_from(CatalogItem).where(CatalogItem.created_by.is_(None))
        )
        == 1
    )
    for model in (Expense, MediaFile):
        assert (
            await count(select(func.count()).select_from(model).where(model.owner_id == user_id))
            == 0
        )
    # The user's own price snapshots survive with created_by nulled out; they
    # hung off the personal item, which is gone, so nothing is left.
    assert (
        await count(
            select(func.count())
            .select_from(MarketPriceSnapshot)
            .where(MarketPriceSnapshot.created_by == user_id)
        )
        == 0
    )

    # No dangling collection item anywhere in the table.
    orphans = await db_session.execute(
        text(
            "SELECT count(*) FROM collection_items ci "
            "LEFT JOIN catalog_items c ON c.id = ci.catalog_item_id "
            "WHERE c.id IS NULL"
        )
    )
    assert orphans.scalar_one() == 0


async def test_foreign_key_still_blocks_a_dangling_collection_item(
    db_session: AsyncSession,
) -> None:
    """NO ACTION defers the check, it does not remove it."""
    user_id = await _build_user_with_personal_items(db_session)
    result = await db_session.execute(
        select(CatalogItem.id).where(CatalogItem.created_by == user_id)
    )
    personal_id = result.scalar_one()

    with pytest.raises(Exception) as caught:
        await db_session.execute(
            text("DELETE FROM catalog_items WHERE id = :id"), {"id": personal_id}
        )
        await db_session.flush()
    assert "foreign key" in str(caught.value).lower()
