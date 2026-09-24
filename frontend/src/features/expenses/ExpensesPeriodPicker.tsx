import { useTranslation } from 'react-i18next';

import { Input, Tabs } from '@/shared/ui';
import type { TabOption } from '@/shared/ui';

import type { ExpensesPeriodPreset } from './period';
import styles from './ExpensesPeriodPicker.module.css';

interface Props {
  /** `null` once the date fields no longer match any preset — no pill stays lit. */
  preset: ExpensesPeriodPreset | null;
  dateFrom: string;
  dateTo: string;
  onPreset: (preset: ExpensesPeriodPreset) => void;
  onCustomRange: (dateFrom: string, dateTo: string) => void;
  invalidRange: boolean;
  /** Use horizontal labels in the full desktop screen, not in compact demos. */
  inlineLabels?: boolean;
}

export function ExpensesPeriodPicker({
  preset,
  dateFrom,
  dateTo,
  onPreset,
  onCustomRange,
  invalidRange,
  inlineLabels = false,
}: Props) {
  const { t } = useTranslation();
  const options: TabOption<ExpensesPeriodPreset | ''>[] = [
    { value: '1m', label: t('expenses.period1m') },
    { value: '3m', label: t('expenses.period3m') },
    { value: '6m', label: t('expenses.period6m') },
    { value: '1y', label: t('expenses.period1y') },
  ];

  return (
    <div className={`${styles.picker} ${inlineLabels ? styles.inlineLabels : ''}`}>
      <Tabs
        options={options}
        value={preset ?? ''}
        onChange={(value) => {
          if (value) onPreset(value);
        }}
        aria-label={t('expenses.periodLabel')}
      />
      <div className={styles.customRange}>
        <div className={styles.dateField}>
          <Input
            type="date"
            label={t('expenses.periodFrom')}
            value={dateFrom}
            max={dateTo}
            onChange={(event) => onCustomRange(event.target.value, dateTo)}
          />
        </div>
        <span className={styles.dash} aria-hidden="true">
          –
        </span>
        <div className={styles.dateField}>
          <Input
            type="date"
            label={t('expenses.periodTo')}
            value={dateTo}
            min={dateFrom}
            onChange={(event) => onCustomRange(dateFrom, event.target.value)}
          />
        </div>
      </div>
      {invalidRange ? <p className={styles.error}>{t('expenses.periodInvalid')}</p> : null}
    </div>
  );
}
