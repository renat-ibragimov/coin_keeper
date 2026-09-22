import { Check } from 'lucide-react';
import { useEffect, useId, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { PeriodFilterValue, PeriodMode } from '@/shared/lib/periodFilter';
import { hasPeriodValue } from '@/shared/lib/periodFilter';

import { Combobox } from './Combobox';
import { Input } from './Input';
import panelStyles from './PeriodFilter.module.css';
import selectStyles from './Select.module.css';

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
  const { t } = useTranslation();
  const autoId = useId();
  const labelId = `${autoId}-label`;

  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

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
    return `${value.dateFrom ?? '…'}–${value.dateTo ?? '…'}`;
  })();

  return (
    <div className={selectStyles.wrapper} ref={rootRef}>
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
                  <Input
                    type="date"
                    value={value.dateFrom ?? ''}
                    max={value.dateTo}
                    onChange={(event) =>
                      onChange({ ...value, dateFrom: event.target.value || undefined })
                    }
                    aria-label={t('catalog.yearFrom')}
                  />
                  <span className={panelStyles.dash}>—</span>
                  <Input
                    type="date"
                    value={value.dateTo ?? ''}
                    min={value.dateFrom}
                    onChange={(event) =>
                      onChange({ ...value, dateTo: event.target.value || undefined })
                    }
                    aria-label={t('catalog.yearTo')}
                  />
                </>
              ) : null}
            </div>

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
