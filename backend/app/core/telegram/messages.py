"""What the admin bot says.

Ukrainian, and the only user-facing wording in the codebase that does not live
in the frontend locale files: the bot is not part of the application interface
and has no locale of its own (docs/13-admin.md, 2.6).

A good run is one short paragraph; the reasoning is in 2.4 -- the nightly log
is three hundred lines long and nobody wants it in a chat. Only a run that
went badly explains itself.
"""

from __future__ import annotations

from typing import Any

from app.models.jobs import JobRun

# Job names as a person would say them. An unknown job still gets a report,
# under its own technical name.
JOB_LABELS = {
    "update-prices": "Оновлення цін",
    "nbu-catalog-sync": "Оновлення каталогу",
}

STATUS_HEADS = {
    "ok": "✅ {job} — усе гаразд",
    "partial": "⚠️ {job} — частково",
    "failed": "⛔️ {job} — не вдалося",
    "running": "▶️ {job} — розпочато",
}


def plural(count: int, one: str, few: str, many: str) -> str:
    """Ukrainian plural for a counted noun: 1 серія, 2 серії, 5 серій."""
    tail_two = count % 100
    if 11 <= tail_two <= 14:
        return many
    tail = count % 10
    if tail == 1:
        return one
    if 2 <= tail <= 4:
        return few
    return many


def counted(count: int, one: str, few: str, many: str) -> str:
    return f"{count} {plural(count, one, few, many)}"


def format_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} с"
    minutes = round(seconds / 60)
    if minutes < 60:
        return f"{minutes} хв"
    hours, rest = divmod(minutes, 60)
    return f"{hours} год {rest} хв" if rest else f"{hours} год"


def _int(stats: dict[str, Any], key: str) -> int | None:
    value = stats.get(key)
    return value if isinstance(value, int) else None


def _price_run_lines(stats: dict[str, Any]) -> list[str]:
    """The counters of the nightly price pass, read the way they are meant.

    no_quote and no_link are ordinary: ua-coins does not quote every coin every
    day. Neither belongs in an alarm, so they are stated, not flagged
    (docs/13-admin.md, section 3).
    """
    lines: list[str] = []
    scope, series = _int(stats, "scope"), _int(stats, "series")
    country = stats.get("country")
    scope_parts = [str(country)] if isinstance(country, str) and country else []
    if series is not None:
        scope_parts.append(counted(series, "серія", "серії", "серій"))
    if scope is not None:
        scope_parts.append(counted(scope, "монета", "монети", "монет"))
    if scope_parts:
        lines.append(", ".join(scope_parts) + ".")

    inserted, corrected = _int(stats, "inserted"), _int(stats, "corrected")
    done: list[str] = []
    if inserted:
        done.append(f"записано {counted(inserted, 'ціну', 'ціни', 'цін')}")
    if corrected:
        done.append(f"виправлено {counted(corrected, 'ціну', 'ціни', 'цін')}")
    if not done:
        done.append("нових цін немає")
    no_quote = _int(stats, "no_quote") or 0
    if no_quote:
        done.append(f"{counted(no_quote, 'монета', 'монети', 'монет')} без котирування")
    lines.append(", ".join(done).capitalize() + ".")
    return lines


def _generic_lines(run: JobRun) -> list[str]:
    return [run.summary] if run.summary else []


def job_run_message(run: JobRun, admin_url: str | None = None) -> str:
    """One finished run, as a person reads it."""
    job_label = JOB_LABELS.get(run.job, run.job)
    head = STATUS_HEADS.get(run.status, "{job}").format(job=job_label)

    stats = run.stats if isinstance(run.stats, dict) else {}
    lines = _price_run_lines(stats) if run.job == "update-prices" and stats else _generic_lines(run)

    if run.finished_at and run.started_at:
        seconds = int((run.finished_at - run.started_at).total_seconds())
        lines.append(f"Тривало {format_duration(seconds)}.")

    if run.status != "ok":
        if run.details:
            lines.append("")
            lines.append(run.details.strip()[:800])
        if admin_url:
            lines.append("")
            lines.append(f"Подробиці: {admin_url}")

    return "\n".join([head, *lines])


def link_confirmed_message() -> str:
    return (
        "✅ Готово. Цей чат отримуватиме звіти про фонові задачі "
        "Bakost Numismatics.\n\n"
        "Команда /last покаже останній прогін."
    )


def no_runs_message() -> str:
    return "Прогонів ще немає."
