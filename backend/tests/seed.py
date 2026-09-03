"""Builders for reference and catalog data used by the stage 3 API tests.

Everything goes through the SQLAlchemy session that the test client shares, so
seeded rows are visible to API calls and disappear with the per-test rollback.

Each helper commits (a savepoint on the outer test transaction) and detaches
what it created: a failing API request rolls the session back, which would
both discard un-committed seeds and expire attribute access on anything still
attached — turning a plain `item.id` in a test into a MissingGreenlet error.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    CatalogItem,
    CoinSeries,
    CollectionItem,
    Country,
    Currency,
    Denomination,
    ExchangeRate,
    Expense,
    MarketPriceSnapshot,
    User,
)
from app.models.enums import CollectionGroup, ExpenseCategory, UserRole


@dataclass
class ReferenceData:
    ukraine: Country
    usa: Country
    uah_2: Denomination
    uah_5: Denomination
    cent_1: Denomination
    fauna: CoinSeries
    cities: CoinSeries


async def seed_currencies(session: AsyncSession) -> None:
    for code, name, symbol in (
        ("UAH", "Hryvnia", "₴"),
        ("USD", "US Dollar", "$"),
        ("EUR", "Euro", "€"),
    ):
        session.add(Currency(code=code, name=name, symbol=symbol))
    await session.flush()


async def seed_reference(session: AsyncSession) -> ReferenceData:
    await seed_currencies(session)

    ukraine = Country(name_original="Україна", code="UA")
    usa = Country(name_original="США", code="US")
    session.add_all([ukraine, usa])
    await session.flush()

    uah_2 = Denomination(
        country_id=ukraine.id, currency_code="UAH", value_minor_units=200, label_original="2 гривні"
    )
    uah_5 = Denomination(
        country_id=ukraine.id,
        currency_code="UAH",
        value_minor_units=500,
        label_original="5 гривень",
    )
    cent_1 = Denomination(
        country_id=usa.id, currency_code="USD", value_minor_units=1, label_original="1 cent"
    )
    session.add_all([uah_2, uah_5, cent_1])

    fauna = CoinSeries(country_id=ukraine.id, name_original="Флора і фауна")
    cities = CoinSeries(country_id=ukraine.id, name_original="Міста України")
    session.add_all([fauna, cities])
    await session.commit()

    for obj in (ukraine, usa, uah_2, uah_5, cent_1, fauna, cities):
        session.expunge(obj)
    return ReferenceData(
        ukraine=ukraine,
        usa=usa,
        uah_2=uah_2,
        uah_5=uah_5,
        cent_1=cent_1,
        fauna=fauna,
        cities=cities,
    )


async def make_catalog_item(
    session: AsyncSession,
    *,
    country: Country,
    title: str,
    year: int,
    denomination: Denomination | None = None,
    series: CoinSeries | None = None,
    group: CollectionGroup = CollectionGroup.COMMEMORATIVE,
    created_by: int | None = None,
    is_archived: bool = False,
    archive_reason: str | None = None,
    **fields: object,
) -> CatalogItem:
    item = CatalogItem(
        country_id=country.id,
        denomination_id=denomination.id if denomination else None,
        series_id=series.id if series else None,
        collection_group=group,
        title_original=title,
        issue_year=year,
        created_by=created_by,
        is_archived=is_archived,
        archived_at=datetime.now(UTC) if is_archived else None,
        archive_reason=archive_reason if is_archived else None,
        **fields,
    )
    session.add(item)
    await session.commit()
    session.expunge(item)
    return item


async def add_snapshot(
    session: AsyncSession,
    item: CatalogItem,
    price: str,
    *,
    currency: str = "UAH",
    observed_at: datetime | None = None,
    created_by: int | None = None,
    is_suspect: bool = False,
    source: str = "UA-Coins",
    grade: str | None = None,
    source_url: str | None = None,
) -> MarketPriceSnapshot:
    snapshot = MarketPriceSnapshot(
        catalog_item_id=item.id,
        source=source,
        grade=grade,
        source_url=source_url,
        price=Decimal(price),
        currency_code=currency,
        observed_at=observed_at or datetime.now(UTC),
        created_by=created_by,
        is_suspect=is_suspect,
    )
    session.add(snapshot)
    await session.commit()
    session.expunge(snapshot)
    return snapshot


async def add_rate(
    session: AsyncSession, code: str, rate: str, effective_date: date
) -> ExchangeRate:
    row = ExchangeRate(
        currency_code=code,
        rate_uah=Decimal(rate),
        effective_date=effective_date,
        fetched_at=datetime.now(UTC),
    )
    session.add(row)
    await session.commit()
    session.expunge(row)
    return row


async def add_collection_item(
    session: AsyncSession,
    *,
    owner_id: int,
    item: CatalogItem,
    quantity: int = 1,
    price: str = "0",
    currency: str = "UAH",
    rate_uah: str = "1",
    acquisition_date: date | None = None,
    with_expense: bool = True,
) -> CollectionItem:
    """Insert an instance the way the purchase transaction would have."""
    row = CollectionItem(
        owner_id=owner_id,
        catalog_item_id=item.id,
        quantity=quantity,
        purchase_price=Decimal(price),
        purchase_currency=currency,
        purchase_rate_uah=Decimal(rate_uah),
        acquisition_date=acquisition_date or date(2024, 1, 15),
    )
    session.add(row)
    await session.flush()
    if with_expense:
        session.add(
            Expense(
                owner_id=owner_id,
                category=ExpenseCategory.COIN_PURCHASE,
                amount=Decimal(price) * quantity,
                currency_code=currency,
                rate_uah=Decimal(rate_uah),
                expense_date=acquisition_date or date(2024, 1, 15),
                catalog_item_id=item.id,
                collection_item_id=row.id,
            )
        )
    await session.commit()
    session.expunge(row)
    return row


async def promote_to_admin(session: AsyncSession, email: str) -> None:
    await session.execute(update(User).where(User.email == email).values(role=UserRole.ADMIN))
    await session.commit()


async def user_id_by_email(session: AsyncSession, email: str) -> int:
    from sqlalchemy import select

    result = await session.execute(select(User.id).where(User.email == email))
    return int(result.scalar_one())
