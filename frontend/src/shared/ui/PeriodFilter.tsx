// Load calendar defaults before our token-based overrides, with the filter.
import 'react-day-picker/style.css';
import { isValid, parse } from 'date-fns';
import { Check } from 'lucide-react';
import { useEffect, useId, useRef, useState } from 'react';
import { DayPicker } from 'react-day-picker';
import { enUS, uk } from 'react-day-picker/locale';
import { useTranslation } from 'react-i18next';

import type { PeriodFilterValue, PeriodMode } from '@/shared/lib/periodFilter';
import {
  formatPeriodDate,
  formatPeriodDateForDisplay,
  hasPeriodValue,
  parsePeriodDate,
  periodDateFormat,
} from '@/shared/lib/periodFilter';

import { Combobox } from './Combobox';
import { Input } from './Input';
import panelStyles from './PeriodFilter.module.css';
import selectStyles from './Select.module.css';

const DAY_PICKER_LOCALES: Record<string, typeof enUS> = { uk, en: enUS };

interface PeriodFilterProps {
  value: PeriodFilterValue;
  onChange: (value: PeriodFilterValue) => void;
  /** Suggestion list for the "year" mode's single field. */
  yearOptions: string[];
  /** Suggestion lists for the "year range" mode's pair — narrowed against
   *  each other by the caller the same way the old two-Combobox field was. */
  yearFromOptions: string[];
  yearToOptions: string[];
}

const MODES: PeriodMode[] = ['year', 'yearRange', 'dateRange'];

function numberOrUndefined(raw: string): number | undefined {
  const value = Number.parseInt(raw, 10);
  return Number.isFinite(value) && value > 0 ? value : undefined;
}

/**
 * Composite "period" filter — one dropdown, same trigger/menu chrome as
 * `Select`/`MultiSelect` (docs/08-ui-map.md): the panel holds a mode list
 * (exact year / year range / full date range) and, below it, the field(s)
 * that mode needs. Switching modes keeps the other modes' own values in
 * `value` untouched — only the active mode's fields render, so an
 * accidental click never loses what was typed.
 */
export function PeriodFilter({
  value,
  onChange,
  yearOptions,
  yearFromOptions,
  yearToOptions,
}: PeriodFilterProps) {
  const { t, i18n } = useTranslation();
  const autoId = useId();
  const labelId = `${autoId}-label`;

  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  const dateFormat = periodDateFormat(i18n.language);
  const rdpLocale = DAY_PICKER_LOCALES[i18n.language] ?? enUS;
  // Same bounds the "year"/"year range" modes already narrow their own
  // suggestion lists to for the selected country — `yearOptions` is that
  // list, oldest first (shared/lib/yearRange.ts).
  const calendarMinYear = Number(yearOptions[0] ?? 1900);
  const calendarMaxYear = Number(yearOptions[yearOptions.length - 1] ?? new Date().getFullYear());

  // A typed-text buffer per field, separate from the committed `yyyy-MM-dd`
  // value: while the owner is still typing "22.09.202", that string doesn't
  // parse yet and must not be thrown away, the same reasoning the search
  // box's own debounce buffer follows elsewhere in this toolbar. Synced back
  // from `value` on every external change (a calendar click, switching
  // modes, "Очистити", the app's language toggle).
  const [fromText, setFromText] = useState(
    () => formatPeriodDateForDisplay(value.dateFrom, i18n.language) ?? '',
  );
  const [toText, setToText] = useState(
    () => formatPeriodDateForDisplay(value.dateTo, i18n.language) ?? '',
  );
  useEffect(() => {
    setFromText(formatPeriodDateForDisplay(value.dateFrom, i18n.language) ?? '');
  }, [value.dateFrom, i18n.language]);
  useEffect(() => {
    setToText(formatPeriodDateForDisplay(value.dateTo, i18n.language) ?? '');
  }, [value.dateTo, i18n.language]);

  const commitTypedDate = (raw: string, field: 'dateFrom' | 'dateTo') => {
    if (raw === '') {
      onChange({ ...value, [field]: undefined });
      return;
    }
    const parsed = parse(raw, dateFormat, new Date());
    if (isValid(parsed)) onChange({ ...value, [field]: formatPeriodDate(parsed) });
  };

  // Which endpoint the calendar's own clicks currently move — react-day-picker's
  // built-in `mode="range"` moves whichever endpoint is "closer" to the
  // clicked day once a range is already complete, with no visible sign of
  // which one that will be and no way to aim it at "від" specifically
  // (owner's report, 2026-09-22). Clicking a text field claims it instead:
  // predictable, and it's how the field itself already works for typing.
  const [activeField, setActiveField] = useState<'dateFrom' | 'dateTo'>('dateFrom');
  useEffect(() => {
    if (!value.dateFrom && !value.dateTo) setActiveField('dateFrom');
  }, [value.dateFrom, value.dateTo]);

  const handleDayClick = (day: Date) => {
    const clicked = formatPeriodDate(day);
    if (activeField === 'dateTo') {
      // A "to" before the current "from" reads as moving the start
      // earlier, not as an error — swap rather than reject the click.
      if (value.dateFrom && clicked < value.dateFrom) {
        onChange({ ...value, dateFrom: clicked, dateTo: value.dateFrom });
      } else {
        onChange({ ...value, dateTo: clicked });
      }
      return;
    }
    const hadTo = value.dateTo !== undefined;
    if (value.dateTo && clicked > value.dateTo) {
      // A "from" past the current "to" starts a fresh range instead of
      // producing an inverted one silently.
      onChange({ ...value, dateFrom: clicked, dateTo: undefined });
      setActiveField('dateTo');
      return;
    }
    onChange({ ...value, dateFrom: clicked });
    // Only the first click of a brand new range auto-advances — editing
    // "від" on an already-complete range stays on "від" until the owner
    // explicitly clicks into "до" (the whole point of tracking this).
    if (!hadTo) setActiveField('dateTo');
  };

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false);
        triggerRef.current?.focus();
      }
    };
    document.addEventListener('pointerdown', onPointer);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('pointerdown', onPointer);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const modeLabel = (mode: PeriodMode) =>
    mode === 'year'
      ? t('catalog.periodModeYear')
      : mode === 'yearRange'
        ? t('catalog.periodModeYearRange')
        : t('catalog.periodModeDateRange');

  const triggerText = (() => {
    if (value.mode === 'year') {
      return value.year !== undefined ? String(value.year) : modeLabel('year');
    }
    if (value.mode === 'yearRange') {
      if (value.yearFrom === undefined && value.yearTo === undefined) return modeLabel('yearRange');
      return `${value.yearFrom ?? '…'}–${value.yearTo ?? '…'}`;
    }
    if (!value.dateFrom && !value.dateTo) return modeLabel('dateRange');
    const from = formatPeriodDateForDisplay(value.dateFrom, i18n.language) ?? '…';
    const to = formatPeriodDateForDisplay(value.dateTo, i18n.language) ?? '…';
    return `${from}–${to}`;
  })();

  return (
    <div className={[selectStyles.wrapper, panelStyles.wrapper].join(' ')} ref={rootRef}>
      <span className={[selectStyles.label, selectStyles.labelCenter].join(' ')} id={labelId}>
        {t('catalog.period')}
      </span>
      <div className={selectStyles.control}>
        <button
          type="button"
          ref={triggerRef}
          className={[selectStyles.trigger, open ? selectStyles.triggerOpen : '']
            .filter(Boolean)
            .join(' ')}
          aria-haspopup="true"
          aria-expanded={open}
          aria-labelledby={labelId}
          onClick={() => setOpen((current) => !current)}
        >
          <span className={selectStyles.triggerText}>{triggerText}</span>
          <span className={selectStyles.arrow} aria-hidden="true" />
        </button>

        {open ? (
          <div className={panelStyles.panel}>
            <div className={selectStyles.list} role="listbox" aria-labelledby={labelId}>
              {MODES.map((mode) => (
                <button
                  key={mode}
                  type="button"
                  role="option"
                  aria-selected={value.mode === mode}
                  className={[
                    selectStyles.option,
                    panelStyles.modeButton,
                    value.mode === mode ? selectStyles.optionSelected : '',
                  ]
                    .filter(Boolean)
                    .join(' ')}
                  onClick={() => onChange({ ...value, mode })}
                >
                  <span className={selectStyles.optionText}>{modeLabel(mode)}</span>
                  {value.mode === mode ? (
                    <span className={selectStyles.check} aria-hidden="true">
                      <Check strokeWidth={2.25} />
                    </span>
                  ) : null}
                </button>
              ))}
            </div>

            <div className={panelStyles.fields}>
              {value.mode === 'year' ? (
                <Combobox
                  inputMode="numeric"
                  options={yearOptions}
                  placeholder={t('catalog.periodModeYear')}
                  value={value.year !== undefined ? String(value.year) : ''}
                  onChange={(event) =>
                    onChange({ ...value, year: numberOrUndefined(event.target.value) })
                  }
                  aria-label={t('catalog.periodModeYear')}
                />
              ) : null}

              {value.mode === 'yearRange' ? (
                <>
                  <Combobox
                    inputMode="numeric"
                    options={yearFromOptions}
                    placeholder={t('catalog.yearFrom')}
                    value={value.yearFrom !== undefined ? String(value.yearFrom) : ''}
                    onChange={(event) =>
                      onChange({ ...value, yearFrom: numberOrUndefined(event.target.value) })
                    }
                    aria-label={t('catalog.yearFrom')}
                  />
                  <span className={panelStyles.dash}>—</span>
                  <Combobox
                    inputMode="numeric"
                    options={yearToOptions}
                    placeholder={t('catalog.yearTo')}
                    value={value.yearTo !== undefined ? String(value.yearTo) : ''}
                    onChange={(event) =>
                      onChange({ ...value, yearTo: numberOrUndefined(event.target.value) })
                    }
                    aria-label={t('catalog.yearTo')}
                  />
                </>
              ) : null}

              {value.mode === 'dateRange' ? (
                <>
                  {/* A wrapping div, not a className on Input itself: Input's
                   * className lands on the <input>, one level below the box
                   * that actually needs the min-width — the flex item
                   * `.fields` sizes as its row (docs/08-ui-map.md). Plain
                   * text, not the native `<input type="date">` these used to
                   * be: its own calendar and placeholder followed the
                   * browser's language, not the app's uk/en toggle, and no
                   * amount of `lang` on the element changed that (owner's
                   * report, 2026-09-22) — react-day-picker below replaces it
                   * precisely so typing and the calendar both track
                   * `i18n.language` for real. */}
                  <div className={panelStyles.dateField}>
                    <Input
                      type="text"
                      inputMode="numeric"
                      placeholder={dateFormat}
                      value={fromText}
                      onChange={(event) => commitTypedDate(event.target.value, 'dateFrom')}
                      onFocus={() => setActiveField('dateFrom')}
                      aria-label={t('catalog.yearFrom')}
                    />
                  </div>
                  <span className={panelStyles.dash}>—</span>
                  <div className={panelStyles.dateField}>
                    <Input
                      type="text"
                      inputMode="numeric"
                      placeholder={dateFormat}
                      value={toText}
                      onChange={(event) => commitTypedDate(event.target.value, 'dateTo')}
                      onFocus={() => setActiveField('dateTo')}
                      aria-label={t('catalog.yearTo')}
                    />
                  </div>
                </>
              ) : null}
            </div>

            {value.mode === 'dateRange' ? (
              <div className={panelStyles.calendar}>
                <p className={panelStyles.calendarHint}>
                  {activeField === 'dateFrom'
                    ? t('catalog.periodPickFrom')
                    : t('catalog.periodPickTo')}
                </p>
                <DayPicker
                  mode="range"
                  locale={rdpLocale}
                  // Month/year dropdowns, not just prev/next arrows: the
                  // catalog's own years reach back to 1900, and clicking
                  // "previous month" a hundred years back is not a real way
                  // to get there (owner's report, 2026-09-22). Bounded to
                  // the same year range the "year"/"year range" modes
                  // already narrow to for the selected country
                  // (`yearOptions`, oldest first), so the dropdown never
                  // offers a decade this country has no coins in.
                  captionLayout="dropdown"
                  navLayout="after"
                  startMonth={new Date(calendarMinYear, 0)}
                  endMonth={new Date(calendarMaxYear, 11)}
                  defaultMonth={parsePeriodDate(value.dateFrom) ?? new Date()}
                  selected={{
                    from: parsePeriodDate(value.dateFrom),
                    to: parsePeriodDate(value.dateTo),
                  }}
                  // Not `onSelect`: DayPicker's own range logic decides which
                  // endpoint a click moves once a range is complete, by
                  // proximity — invisible to the owner and not steerable
                  // toward "від" specifically. `onDayClick` is the raw
                  // per-day event, independent of that logic, so
                  // `handleDayClick` above can apply `activeField` instead.
                  onDayClick={handleDayClick}
                />
              </div>
            ) : null}

            {hasPeriodValue(value) ? (
              <div
                className={selectStyles.clearRow}
                role="button"
                tabIndex={0}
                onClick={() => onChange({ mode: value.mode })}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    onChange({ mode: value.mode });
                  }
                }}
              >
                {t('catalog.periodClear')}
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}
