import { api, toQuery } from '@/shared/api/client';
import type { JobRunOut, JobRunsPage } from '@/shared/api/types';

export const PAGE_SIZE = 20;

/**
 * A run still open long after it should have closed is how a dead job shows
 * up here: nothing reports its own death, so an unclosed row is the evidence.
 * Six hours is comfortably longer than the nightly price pass has ever taken
 * and far shorter than the day between two of them (docs/13-admin.md, 2.7).
 */
export const STALE_AFTER_MS = 6 * 60 * 60 * 1000;

export function fetchJobRuns(params: { job?: string; page: number }): Promise<JobRunsPage> {
  return api<JobRunsPage>(
    `/admin/jobs${toQuery({ job: params.job, page: params.page, pageSize: PAGE_SIZE })}`,
  );
}

export function fetchJobRun(id: number): Promise<JobRunOut> {
  return api<JobRunOut>(`/admin/jobs/${id}`);
}

export function isStale(run: JobRunOut, now: number = Date.now()): boolean {
  return run.status === 'running' && now - new Date(run.startedAt).getTime() > STALE_AFTER_MS;
}

/** Milliseconds a run took, or null while it is still going. */
export function runDuration(run: JobRunOut): number | null {
  if (!run.finishedAt) return null;
  return new Date(run.finishedAt).getTime() - new Date(run.startedAt).getTime();
}
