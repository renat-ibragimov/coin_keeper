import { useTranslation } from 'react-i18next';

import type { JobRunOut } from '@/shared/api/types';
import { Badge, Modal, PropertyList } from '@/shared/ui';
import type { PropertyRow } from '@/shared/ui';

import styles from './JobRunDialog.module.css';
import { formatDuration, formatMoment, statsRows, statusTone } from './jobRunView';

/** One run in full: the counters it reported and, when it went badly, why. */
export function JobRunDialog({ run, onClose }: { run: JobRunOut; onClose: () => void }) {
  const { t, i18n } = useTranslation();

  const rows: PropertyRow[] = [
    { key: 'job', label: t('admin.jobs.job'), value: run.job },
    {
      key: 'started',
      label: t('admin.jobs.started'),
      value: formatMoment(run.startedAt, i18n.language),
    },
    {
      key: 'finished',
      label: t('admin.jobs.finished'),
      value: run.finishedAt ? formatMoment(run.finishedAt, i18n.language) : '—',
    },
    { key: 'duration', label: t('admin.jobs.duration'), value: formatDuration(run, t) ?? '—' },
    ...(run.runDate
      ? [{ key: 'runDate', label: t('admin.jobs.runDate'), value: run.runDate }]
      : []),
    ...(run.exitCode === null || run.exitCode === undefined
      ? []
      : [{ key: 'exitCode', label: t('admin.jobs.exitCode'), value: String(run.exitCode) }]),
  ];

  const counters = statsRows(run);

  return (
    <Modal
      open
      onClose={onClose}
      title={
        <span className={styles.title}>
          {t('admin.jobs.runTitle', { id: run.id })}
          <Badge tone={statusTone(run)}>{t(`admin.jobs.statuses.${run.status}`)}</Badge>
        </span>
      }
    >
      <PropertyList rows={rows} />

      {run.summary ? <pre className={styles.summary}>{run.summary}</pre> : null}

      {counters.length > 0 ? (
        <>
          <h3 className={styles.subhead}>{t('admin.jobs.counters')}</h3>
          <dl className={styles.counters}>
            {counters.map((row) => (
              <div key={row.key} className={styles.counter}>
                <dt>{row.key}</dt>
                <dd>{row.value}</dd>
              </div>
            ))}
          </dl>
        </>
      ) : null}

      {run.details ? (
        <>
          <h3 className={styles.subhead}>{t('admin.jobs.details')}</h3>
          <pre className={styles.details}>{run.details}</pre>
        </>
      ) : null}
    </Modal>
  );
}
