"""Expense endpoints (docs/03-api-contract.md)."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, DbSession, Pagination
from app.api.errors import ProblemError
from app.models.enums import ExpenseCategory
from app.repositories.expenses import ExpenseFilters
from app.schemas.common import Page
from app.schemas.expenses import (
    ExpenseCreate,
    ExpenseOut,
    ExpensesSummaryOut,
    ExpenseUpdate,
)
from app.services.expenses import (
    BadReferenceError,
    CoinPurchaseManagedError,
    ExpenseNotFoundError,
    ExpenseService,
    MissingRateError,
    UnknownCurrencyError,
)

router = APIRouter(prefix="/expenses", tags=["expenses"])


def _not_found() -> ProblemError:
    return ProblemError(
        status.HTTP_404_NOT_FOUND, "expense-not-found", "Not found", "The expense does not exist."
    )


def _conflict(detail: str) -> ProblemError:
    return ProblemError(status.HTTP_409_CONFLICT, "coin-purchase-managed", "Conflict", detail)


def _unprocessable(problem_type: str, detail: str) -> ProblemError:
    return ProblemError(
        status.HTTP_422_UNPROCESSABLE_CONTENT, problem_type, "Request rejected", detail
    )


@router.get("")
async def list_expenses(
    session: DbSession,
    user: CurrentUser,
    pagination: Pagination,
    category: Annotated[ExpenseCategory | None, Query()] = None,
    date_from: Annotated[date | None, Query(alias="dateFrom")] = None,
    date_to: Annotated[date | None, Query(alias="dateTo")] = None,
) -> Page[ExpenseOut]:
    filters = ExpenseFilters(category=category, date_from=date_from, date_to=date_to)
    items, total = await ExpenseService(session, user).list_expenses(
        filters, limit=pagination.page_size, offset=pagination.offset
    )
    return Page(items=items, total=total, page=pagination.page, page_size=pagination.page_size)


@router.get("/summary")
async def expenses_summary(session: DbSession, user: CurrentUser) -> ExpensesSummaryOut:
    return await ExpenseService(session, user).summary()


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_expense(
    session: DbSession, user: CurrentUser, payload: ExpenseCreate
) -> ExpenseOut:
    try:
        return await ExpenseService(session, user).create(payload)
    except CoinPurchaseManagedError as exc:
        raise _conflict(exc.detail) from exc
    except UnknownCurrencyError as exc:
        raise _unprocessable("unknown-currency", exc.detail) from exc
    except MissingRateError as exc:
        raise _unprocessable("exchange-rate-missing", exc.detail) from exc
    except BadReferenceError as exc:
        raise _unprocessable("invalid-reference", exc.detail) from exc


@router.patch("/{expense_id}")
async def update_expense(
    session: DbSession, user: CurrentUser, expense_id: int, payload: ExpenseUpdate
) -> ExpenseOut:
    try:
        return await ExpenseService(session, user).update(expense_id, payload)
    except ExpenseNotFoundError as exc:
        raise _not_found() from exc
    except CoinPurchaseManagedError as exc:
        raise _conflict(exc.detail) from exc
    except UnknownCurrencyError as exc:
        raise _unprocessable("unknown-currency", exc.detail) from exc
    except MissingRateError as exc:
        raise _unprocessable("exchange-rate-missing", exc.detail) from exc
    except BadReferenceError as exc:
        raise _unprocessable("invalid-reference", exc.detail) from exc


@router.delete("/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_expense(session: DbSession, user: CurrentUser, expense_id: int) -> None:
    try:
        await ExpenseService(session, user).delete(expense_id)
    except ExpenseNotFoundError as exc:
        raise _not_found() from exc
    except CoinPurchaseManagedError as exc:
        raise _conflict(exc.detail) from exc
