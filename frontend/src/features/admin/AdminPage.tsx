import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { AlertTriangle, ListChecks } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';

import type { JobRunOut } from '@/shared/api/types';
import {
  Badge,
  Card,
  DataTable,
  EmptyState,
  ErrorState,
  PageHeader,
  Pagination,
  Select,
  Skeleton,
} from '@/shared/ui';

import styles from './AdminPage.module.css';
import { fetchJobRuns, isStale, PAGE_SIZE } from './api';
import { JobRunDialog } from './JobRunDialog';
import { TelegramCard } from './TelegramCard';
import { formatDuration, formatMoment, statusTone } from './jobRunView';

const ALL_JOBS = '';

export function AdminPage() {
  const { t, i18n } = useTranslation();
  const [params, setParams] = useSearchParams();
  const [openRun, setOpenRun] = useState<JobRunOut | null>(null);

  const job = params.get('job') ?? ALL_JOBS;
  const page = Number(params.get('page') ?? 1);

  const query = useQuery({
    queryKey: ['admin-jobs', job, page],
    queryFn: () => fetchJobRuns({ job: job || undefined, page }),
    placeholderData: keepPreviousData,
  });

  function setParam(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    // Any change of filter starts the listing over: page 4 of the old filter
    // is rarely page 4 of the new one.
    if (key !== 'page') next.delete('page');
    setParams(next, { replace: true });
  }

  return (
    <div className={styles.page}>
      <PageHeader title={t('admin.title')} subtitle={t('admin.subtitle')} />

      <TelegramCard />

      <Card variant="panel">
        <div className={styles.sectionHead}>
          <h2 className={styles.sectionTitle}>{t('admin.jobs.title')}</h2>
          {(query.data?.jobs.length ?? 0) > 1 ? (
            <Select
              aria-label={t('admin.jobs.filterLabel')}
              value={job}
              onChange={(event) => setParam('job', event.target.value)}
            >
              <option value={ALL_JOBS}>{t('admin.jobs.allJobs')}</option>
              {query.data?.jobs.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </Select>
          ) : null}
        </div>

        {query.isPending ? <Skeleton height={220} /> : null}
        {query.isError ? <ErrorState onRetry={() => void query.refetch()} /> : null}

        {query.data && query.data.items.length === 0 ? (
          <EmptyState
            title={t('admin.jobs.emptyTitle')}
            description={t('admin.jobs.emptyText')}
            icon={<ListChecks strokeWidth={1.75} />}
          />
        ) : null}

        {query.data && query.data.items.length > 0 ? (
          <>
            <DataTable minWidth={840}>
              <thead>
                <tr>
                  <th className={styles.statusColumn}>{t('admin.jobs.status')}</th>
                  <th className={styles.jobColumn}>{t('admin.jobs.job')}</th>
                  <th className={styles.startedColumn}>{t('admin.jobs.started')}</th>
                  <th className={styles.durationColumn}>{t('admin.jobs.duration')}</th>
                  <th>{t('admin.jobs.summary')}</th>
                </tr>
              </thead>
              <tbody>
                {query.data.items.map((run) => (
                  <tr key={run.id} className={styles.row}>
                    <td className={styles.statusColumn}>
                      <button
                        type="button"
                        className={styles.rowButton}
                        onClick={() => setOpenRun(run)}
                      >
                        <Badge tone={statusTone(run)}>
                          {t(`admin.jobs.statuses.${run.status}`)}
                        </Badge>
                      </button>
                    </td>
                    <td className={styles.jobColumn}>{run.job}</td>
                    <td className={styles.startedColumn}>
                      {formatMoment(run.startedAt, i18n.language)}
                    </td>
                    <td className={styles.durationColumn}>
                      {formatDuration(run, t) ?? <span className={styles.muted}>—</span>}
                    </td>
                    <td className={styles.summaryCell}>
                      {isStale(run) ? (
                        <span className={styles.stale}>
                          <AlertTriangle size={14} strokeWidth={2} aria-hidden="true" />
                          {t('admin.jobs.stale')}
                        </span>
                      ) : (
                        <span className={styles.summary}>{run.summary ?? '—'}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </DataTable>
            <Pagination
              page={query.data.page}
              pageCount={Math.ceil(query.data.total / PAGE_SIZE)}
              onChange={(next) => setParam('page', String(next))}
            />
          </>
        ) : null}
      </Card>

      {openRun ? <JobRunDialog run={openRun} onClose={() => setOpenRun(null)} /> : null}
    </div>
  );
}
