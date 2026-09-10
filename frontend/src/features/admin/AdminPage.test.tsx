import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import '@/shared/i18n';
import type { JobRunOut, JobRunsPage } from '@/shared/api/types';

import { AdminPage } from './AdminPage';
import { fetchJobRuns } from './api';

vi.mock('./api', async () => {
  const actual = await vi.importActual<typeof import('./api')>('./api');
  return { ...actual, fetchJobRuns: vi.fn() };
});

const HOUR = 60 * 60 * 1000;

function makeRun(overrides: Partial<JobRunOut> = {}): JobRunOut {
  return {
    id: 1,
    job: 'update-prices',
    status: 'ok',
    startedAt: '2026-09-10T00:15:00Z',
    finishedAt: '2026-09-10T00:23:00Z',
    runDate: '2026-09-10',
    summary: 'update-prices ok series=8 scope=325 inserted=321 errors=0',
    stats: { scope: 325, inserted: 321, errors: 0 },
    details: null,
    exitCode: 0,
    ...overrides,
  };
}

function makePage(items: JobRunOut[], jobs = ['update-prices']): JobRunsPage {
  return { items, total: items.length, page: 1, pageSize: 20, jobs };
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/admin']}>
        <AdminPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('AdminPage', () => {
  beforeEach(() => {
    vi.mocked(fetchJobRuns).mockReset();
  });

  it('lists runs with their status and summary', async () => {
    vi.mocked(fetchJobRuns).mockResolvedValue(makePage([makeRun()]));
    renderPage();

    expect(await screen.findByText('Успішно')).toBeInTheDocument();
    expect(screen.getByText(/scope=325/)).toBeInTheDocument();
    expect(screen.getByText('update-prices')).toBeInTheDocument();
  });

  it('marks a run that never closed, which is how a dead job shows up', async () => {
    vi.mocked(fetchJobRuns).mockResolvedValue(
      makePage([
        makeRun({
          status: 'running',
          startedAt: new Date(Date.now() - 8 * HOUR).toISOString(),
          finishedAt: null,
          summary: null,
          stats: null,
          exitCode: null,
        }),
      ]),
    );
    renderPage();

    expect(await screen.findByText(/Схоже, зупинилася/)).toBeInTheDocument();
  });

  it('a running job that has only just started is not called stopped', async () => {
    vi.mocked(fetchJobRuns).mockResolvedValue(
      makePage([
        makeRun({
          status: 'running',
          startedAt: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
          finishedAt: null,
          summary: null,
        }),
      ]),
    );
    renderPage();

    expect(await screen.findByText('Виконується')).toBeInTheDocument();
    expect(screen.queryByText(/Схоже, зупинилася/)).not.toBeInTheDocument();
  });

  it('opens one run with its counters and, when it failed, why', async () => {
    vi.mocked(fetchJobRuns).mockResolvedValue(
      makePage([
        makeRun({
          status: 'failed',
          summary: 'update-prices failed errors=1',
          details: 'reading the catalog: connection refused',
          exitCode: 2,
        }),
      ]),
    );
    renderPage();

    await userEvent.click(await screen.findByText('Помилка'));

    expect(await screen.findByText('Прогін №1')).toBeInTheDocument();
    expect(screen.getByText('inserted')).toBeInTheDocument();
    expect(screen.getByText(/connection refused/)).toBeInTheDocument();
  });

  it('shows an empty state before the first run has reported', async () => {
    vi.mocked(fetchJobRuns).mockResolvedValue(makePage([], []));
    renderPage();

    expect(await screen.findByText('Прогонів ще немає')).toBeInTheDocument();
  });
});
