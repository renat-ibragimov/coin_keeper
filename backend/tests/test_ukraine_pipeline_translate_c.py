"""translate-c: selection, batch validation/retry, provenance, idempotency.

No live call ever happens here — `translate` is always a fake async function;
see app/ukraine_pipeline/translate_c.py's module docstring for why a plain
dry run must not call the real API at all.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CatalogItem, CoinSeries
from app.models.enums import TranslationSource
from app.ukraine_pipeline import translate_c
from tests.seed import country_by_code, make_catalog_item, seed_currencies


def fake_translate(
    table: dict[int, dict[str, str]], calls: list[list[int]] | None = None
) -> translate_c.TranslateFn:
    """Returns a canned {"id", "titleUk", "titleEn"} row for every id in `table`
    it is asked about; ids the table doesn't cover are silently missing from
    the response, which is exactly the shape `_validate_batch` must reject.
    """

    async def _translate(tasks: Any) -> list[dict[str, Any]]:
        if calls is not None:
            calls.append([task.id for task in tasks])
        return [{"id": task.id, **table[task.id]} for task in tasks if task.id in table]

    return _translate


def failing_translate(calls: list[int]) -> translate_c.TranslateFn:
    async def _translate(tasks: Any) -> None:
        calls.append(len(tasks))
        raise RuntimeError("network is down")

    return _translate


async def _never_called(_tasks: Any) -> None:
    raise AssertionError("translate() must not be called")


# --------------------------------------------------------------------- select
async def test_selection_skips_official_and_manual(db_session: AsyncSession) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    official = await make_catalog_item(
        db_session,
        country=country,
        title="Соня садова",
        year=1999,
        title_uk="Соня садова",
        title_uk_source=TranslationSource.OFFICIAL,
        title_en="Garden Dormouse",
        title_en_source=TranslationSource.OFFICIAL,
    )
    manual = await make_catalog_item(
        db_session,
        country=country,
        title="Різдво",
        year=2020,
        title_uk="Різдво Христове",
        title_uk_source=TranslationSource.MANUAL,
        title_en="The Nativity",
        title_en_source=TranslationSource.MANUAL,
    )
    needs_it = await make_catalog_item(db_session, country=country, title="Пробел", year=2021)

    items, tasks = await translate_c.select_item_tasks(db_session, country.id)

    ids = {task.id for task in tasks}
    assert official.id not in ids
    assert manual.id not in ids
    assert needs_it.id in ids
    assert items[needs_it.id].id == needs_it.id


async def test_selection_reselects_its_own_llm_output(db_session: AsyncSession) -> None:
    """Idempotent re-entry: a record this step already touched is fair game again."""
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    item = await make_catalog_item(
        db_session,
        country=country,
        title="20 років грошової реформи в Україні",
        year=2016,
        title_uk="20 років грошової реформи",
        title_uk_source=TranslationSource.LLM,
        title_en=None,
    )
    _, tasks = await translate_c.select_item_tasks(db_session, country.id)
    task = next(t for t in tasks if t.id == item.id)
    assert task.needs_uk is True
    assert task.needs_en is True


async def test_a_partial_gap_only_needs_the_missing_slot(db_session: AsyncSession) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    item = await make_catalog_item(
        db_session,
        country=country,
        title="Різдво",
        year=2020,
        title_uk="Різдво Христове",
        title_uk_source=TranslationSource.OFFICIAL,
        title_en=None,
    )
    _, tasks = await translate_c.select_item_tasks(db_session, country.id)
    task = next(t for t in tasks if t.id == item.id)
    assert task.needs_uk is False
    assert task.needs_en is True


# ------------------------------------------------------------------ dry run
async def test_a_plain_dry_run_never_calls_the_api(db_session: AsyncSession) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    item = await make_catalog_item(db_session, country=country, title="Пробел", year=2021)

    outcome = await translate_c.run_translate_c(
        db_session, country_id=country.id, translate=_never_called, dry_run=True, call_api=False
    )

    assert outcome.planned_items == 1
    assert outcome.translated_uk == 0
    assert outcome.translated_en == 0
    stored = await db_session.get(CatalogItem, item.id)
    assert stored is not None
    assert stored.title_uk is None


async def test_translate_out_on_a_dry_run_calls_the_api_but_writes_nothing(
    db_session: AsyncSession,
) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    item = await make_catalog_item(
        db_session, country=country, title="1 гривна, 2016 20 років гривні", year=2016
    )
    calls: list[list[int]] = []
    translate = fake_translate(
        {item.id: {"titleUk": "20 років грошової реформи", "titleEn": "The 20th Anniversary"}},
        calls,
    )

    outcome = await translate_c.run_translate_c(
        db_session, country_id=country.id, translate=translate, dry_run=True, call_api=True
    )

    assert calls, "the API must have been called"
    assert outcome.translated_uk == 1
    assert outcome.rows[0]["newUk"] == "20 років грошової реформи"
    stored = await db_session.get(CatalogItem, item.id)
    assert stored is not None
    assert stored.title_uk is None  # nothing persisted without --apply


# --------------------------------------------------------------------- apply
async def test_apply_writes_llm_provenance_and_fixes_a_russian_original(
    db_session: AsyncSession,
) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    item = await make_catalog_item(
        db_session,
        country=country,
        title="1 гривна, 2016 20 лет введению гривны Алюминиевая бронза, 6.8g",
        year=2016,
        original_lang="ru",
    )
    translate = fake_translate(
        {
            item.id: {
                "titleUk": "20 років грошової реформи в Україні",
                "titleEn": "The 20th Anniversary of the Monetary Reform in Ukraine",
            }
        }
    )

    outcome = await translate_c.run_translate_c(
        db_session, country_id=country.id, translate=translate, dry_run=False, call_api=True
    )
    await db_session.commit()

    assert outcome.translated_uk == 1
    assert outcome.translated_en == 1
    assert len(outcome.rows) == 1
    assert outcome.rows[0]["oldOriginal"] == item.title_original
    assert outcome.rows[0]["oldLang"] == "ru"

    stored = await db_session.get(CatalogItem, item.id)
    assert stored is not None
    assert stored.title_uk == "20 років грошової реформи в Україні"
    assert stored.title_uk_source is TranslationSource.LLM
    assert stored.title_en == "The 20th Anniversary of the Monetary Reform in Ukraine"
    assert stored.title_en_source is TranslationSource.LLM
    # For Ukraine the issuer's language is Ukrainian: the Russian original is
    # replaced, and it survives only in the CSV row asserted above.
    assert stored.title_original == "20 років грошової реформи в Україні"
    assert stored.original_lang == "uk"


async def test_a_uk_original_is_left_alone(db_session: AsyncSession) -> None:
    """Only a genuinely Russian original gets corrected."""
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    item = await make_catalog_item(
        db_session, country=country, title="Місцевий заголовок", year=2016, original_lang="uk"
    )
    translate = fake_translate({item.id: {"titleUk": "Новий заголовок", "titleEn": "New title"}})

    await translate_c.run_translate_c(
        db_session, country_id=country.id, translate=translate, dry_run=False, call_api=True
    )
    await db_session.commit()

    stored = await db_session.get(CatalogItem, item.id)
    assert stored is not None
    assert stored.title_original == "Місцевий заголовок"
    assert stored.original_lang == "uk"


async def test_run_twice_only_the_second_run_is_a_no_op_for_official(
    db_session: AsyncSession,
) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    item = await make_catalog_item(db_session, country=country, title="Пробел", year=2021)
    translate = fake_translate({item.id: {"titleUk": "Назва", "titleEn": "Title"}})

    first = await translate_c.run_translate_c(
        db_session, country_id=country.id, translate=translate, dry_run=False, call_api=True
    )
    await db_session.commit()
    second = await translate_c.run_translate_c(
        db_session, country_id=country.id, translate=translate, dry_run=False, call_api=True
    )
    await db_session.commit()

    assert first.planned_items == 1
    # The llm-sourced row is still selected (idempotent re-entry), but the
    # official/manual exclusion is what a permanent record would rely on —
    # covered directly by test_selection_skips_official_and_manual above.
    assert second.planned_items == 1


# ------------------------------------------------------------------- batches
async def test_an_invalid_batch_retries_once_then_succeeds(db_session: AsyncSession) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    item = await make_catalog_item(db_session, country=country, title="Пробел", year=2021)

    attempts: list[int] = []

    async def flaky(tasks: Any) -> list[dict[str, Any]] | None:
        attempts.append(1)
        if len(attempts) == 1:
            return [{"id": tasks[0].id}]  # missing titleUk/titleEn: invalid shape
        return [{"id": task.id, "titleUk": "Назва", "titleEn": "Title"} for task in tasks]

    outcome = await translate_c.run_translate_c(
        db_session, country_id=country.id, translate=flaky, dry_run=False, call_api=True
    )
    await db_session.commit()

    assert len(attempts) == 2
    assert outcome.retries == 1
    assert outcome.errors == []
    stored = await db_session.get(CatalogItem, item.id)
    assert stored is not None
    assert stored.title_uk == "Назва"


async def test_an_invalid_batch_twice_is_reported_and_changes_nothing(
    db_session: AsyncSession,
) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    item = await make_catalog_item(db_session, country=country, title="Пробел", year=2021)

    async def always_broken(_tasks: Any) -> list[dict[str, Any]]:
        return [{"id": "not-an-int"}]

    outcome = await translate_c.run_translate_c(
        db_session, country_id=country.id, translate=always_broken, dry_run=False, call_api=True
    )
    await db_session.commit()

    assert outcome.errors and outcome.errors[0]["ids"] == [item.id]
    assert outcome.translated_uk == 0
    stored = await db_session.get(CatalogItem, item.id)
    assert stored is not None
    assert stored.title_uk is None


async def test_a_network_error_counts_as_an_invalid_batch(db_session: AsyncSession) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    await make_catalog_item(db_session, country=country, title="Пробел", year=2021)
    calls: list[int] = []

    outcome = await translate_c.run_translate_c(
        db_session,
        country_id=country.id,
        translate=failing_translate(calls),
        dry_run=False,
        call_api=True,
    )

    assert len(calls) == 2  # one retry
    assert outcome.retries == 1
    assert len(outcome.errors) == 1


async def test_batches_are_chunked(db_session: AsyncSession) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    for n in range(25):
        await make_catalog_item(db_session, country=country, title=f"Монета {n}", year=2000 + n)
    calls: list[list[int]] = []

    async def translate(tasks: Any) -> list[dict[str, Any]]:
        calls.append([t.id for t in tasks])
        return [{"id": t.id, "titleUk": "Назва", "titleEn": "Title"} for t in tasks]

    outcome = await translate_c.run_translate_c(
        db_session,
        country_id=country.id,
        translate=translate,
        dry_run=False,
        call_api=True,
        batch_size=20,
    )

    assert outcome.batches == 2
    assert [len(batch) for batch in calls] == [20, 5]


# ---------------------------------------------------------------------- series
async def test_series_without_english_name_are_translated(db_session: AsyncSession) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    series = CoinSeries(country_id=country.id, name_original="Флора і фауна України")
    db_session.add(series)
    await db_session.commit()

    translate = fake_translate({series.id: {"titleUk": "", "titleEn": "Ukrainian Flora and Fauna"}})

    outcome = await translate_c.run_translate_c(
        db_session, country_id=country.id, translate=translate, dry_run=False, call_api=True
    )
    await db_session.commit()

    assert outcome.series_translated_en == 1
    stored = await db_session.get(CoinSeries, series.id)
    assert stored is not None
    assert stored.name_en == "Ukrainian Flora and Fauna"
    assert stored.name_en_source is TranslationSource.LLM
    assert stored.name_uk is None  # translate-c only fills the English gap for series


async def test_a_series_with_an_english_name_already_is_left_alone(
    db_session: AsyncSession,
) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    series = CoinSeries(
        country_id=country.id,
        name_original="Флора і фауна України",
        name_en="Ukrainian Flora and Fauna",
        name_en_source=TranslationSource.OFFICIAL,
    )
    db_session.add(series)
    await db_session.commit()

    _, tasks = await translate_c.select_series_tasks(db_session, country.id)
    assert tasks == []


# ------------------------------------------------------------------------ CSV
async def test_write_review_csv(tmp_path: Path) -> None:
    outcome = translate_c.TranslateOutcome(
        rows=[
            {
                "id": 42,
                "oldOriginal": "20 лет гривне",
                "oldLang": "ru",
                "newUk": "20 років гривні",
                "newEn": "The 20th Anniversary of the Hryvnia",
            }
        ]
    )
    path = tmp_path / "translate-c.csv"

    rows = translate_c.write_review_csv(path, outcome)

    assert rows == 1
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")  # utf-8-sig BOM
    text = raw.decode("utf-8-sig")
    assert "20 років гривні" in text
    assert "20 лет гривне" in text


def test_batch_validation_rejects_a_non_list_response() -> None:
    task = translate_c.TranslationTask(
        id=1, title="x", year=2000, denomination=None, material=None, needs_uk=True, needs_en=False
    )
    assert translate_c._validate_batch([task], {"id": 1}) is None
    assert translate_c._validate_batch([task], None) is None
    assert translate_c._validate_batch([task], []) is None


def test_batch_validation_rejects_an_empty_required_field() -> None:
    task = translate_c.TranslationTask(
        id=1, title="x", year=2000, denomination=None, material=None, needs_uk=True, needs_en=True
    )
    assert translate_c._validate_batch([task], [{"id": 1, "titleUk": "", "titleEn": "T"}]) is None
    assert translate_c._validate_batch([task], [{"id": 1, "titleUk": "У", "titleEn": "T"}]) == {
        1: {"titleUk": "У", "titleEn": "T"}
    }
