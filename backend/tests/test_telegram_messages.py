from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.core.telegram.messages import job_run_message


def catalog_run(*, found: int, drafted: int):
    started = datetime(2026, 9, 21, 10, 0, tzinfo=UTC)
    return SimpleNamespace(
        job="nbu-catalog-sync",
        status="ok",
        stats={"scanned": 25, "new": found, "drafted": drafted},
        summary=f"nbu-catalog-sync scanned=25 new={found} drafted={drafted}",
        details=None,
        started_at=started,
        finished_at=started + timedelta(minutes=2),
    )


def test_catalog_run_with_new_coins_links_to_proposals():
    assert job_run_message(catalog_run(found=2, drafted=2), "https://example.com/admin") == (
        "✅ Оновлення каталогу — усе гаразд\n"
        "Знайдено 2 нові монети.\n"
        "На перевірку додано 2 чернетки.\n\n"
        "Переглянути пропозиції: https://example.com/admin?section=proposals\n"
        "Тривало 2 хв."
    )


def test_catalog_run_without_new_coins_says_so_without_link():
    assert job_run_message(catalog_run(found=0, drafted=0), "https://example.com/admin") == (
        "✅ Оновлення каталогу — усе гаразд\nНових монет не знайдено.\nТривало 2 хв."
    )
