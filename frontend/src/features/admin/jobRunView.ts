import type { TFunction } from 'i18next';

import type { JobRunOut } from '@/shared/api/types';

import { isStale, runDuration } from './api';

/**
 * A run stuck open reads as trouble, not as work in progress: with no watchdog
 * yet, this colour is the whole alarm (docs/13-admin.md, 2.7).
 */
export function statusTone(run: JobRunOut): 'neutral' | 'success' | 'warning' | 'danger' {
  if (run.status === 'ok') return 'success';
  if (run.status === 'partial') return 'warning';
  if (run.status === 'failed') return 'danger';
  return isStale(run) ? 'warning' : 'neutral';
}

export function formatMoment(value: string, locale: string): string {
  return new Date(value).toLocaleString(locale, {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function formatDuration(run: JobRunOut, t: TFunction): string | null {
  const ms = runDuration(run);
  if (ms === null) return null;
  const seconds = Math.max(1, Math.round(ms / 1000));
  if (seconds < 60) return t('admin.jobs.seconds', { count: seconds });
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return t('admin.jobs.minutes', { count: minutes });
  return t('admin.jobs.hours', { count: Math.round(minutes / 60) });
}

/** Counters as rows, in the order the job reported them. */
export function statsRows(run: JobRunOut): { key: string; value: string }[] {
  if (!run.stats) return [];
  return Object.entries(run.stats).map(([key, value]) => ({
    key,
    value: typeof value === 'object' && value !== null ? JSON.stringify(value) : String(value),
  }));
}
