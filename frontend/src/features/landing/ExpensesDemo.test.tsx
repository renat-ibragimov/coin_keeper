import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import i18n from '@/shared/i18n';
import type { ExpensePeriodTotal } from '@/shared/api/types';

import { landingCopy } from './copy';
import { ExpensesDemo } from './ExpensesDemo';
import { expenseDemoChart } from './expenseDemoData';

vi.mock('@/shared/theme/useChartPalette', () => ({ useChartPalette: () => ({}) }));
vi.mock('@/features/expenses/ExpensesByMonthChart', () => ({
  ExpensesByMonthChart: ({ data }: { data: ExpensePeriodTotal[] }) => (
    <output data-testid="chart">
      {data.reduce((sum, row) => sum + Number(row.coinsUah) + Number(row.supportingUah), 0)}
    </output>
  ),
}));

beforeEach(async () => {
  await i18n.changeLanguage('uk');
});

describe('landing expenses preview', () => {
  it('changes chart dates without filtering the journal or the all-time total', async () => {
    const user = userEvent.setup();
    render(<ExpensesDemo c={landingCopy.uk} en={false} />);
    const journal = screen.getByRole('table').textContent;
    expect(screen.getByTestId('chart')).toHaveTextContent('11050');
    await user.click(screen.getByRole('tab', { name: '1М' }));
    expect(screen.getByTestId('chart')).toHaveTextContent('4530');
    expect(screen.getByRole('table').textContent).toBe(journal);
    expect(screen.getByText('Разом на хобі').parentElement).toHaveTextContent(/11\s050/);
  });

  it('filters journal categories without changing the chart and resets pagination', async () => {
    const user = userEvent.setup();
    render(<ExpensesDemo c={landingCopy.uk} en={false} />);
    await user.click(screen.getByRole('button', { name: 'Вперед' }));
    await user.click(screen.getByRole('button', { name: /Доставка/ }));
    const table = screen.getByRole('table');
    expect(within(table).getAllByText('Доставка')).toHaveLength(4);
    expect(within(table).queryByText('Покупка монети')).not.toBeInTheDocument();
    expect(screen.getByTestId('chart')).toHaveTextContent('11050');
    expect(screen.getByRole('button', { name: 'Назад' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Вперед' })).toBeDisabled();
  });

  it('supports a custom empty period without hiding journal entries', () => {
    render(<ExpensesDemo c={landingCopy.uk} en={false} />);
    fireEvent.change(screen.getByLabelText('Період по'), { target: { value: '2025-02-28' } });
    expect(screen.getByText('За цей період витрат не було.')).toBeInTheDocument();
    expect(within(screen.getByRole('table')).getAllByRole('row')).toHaveLength(5);
    expect(screen.getByRole('tab', { name: '6М' })).toHaveAttribute('aria-selected', 'false');
  });
});

describe('expense demo chart aggregation', () => {
  it('agrees with the collection preview and zero-fills missing months', () => {
    const chart = expenseDemoChart('2025-01-01', '2025-06-30');
    expect(chart.granularity).toBe('month');
    expect(chart.byPeriod).toHaveLength(6);
    expect(chart.byPeriod[0]).toEqual({ period: '2025-01', coinsUah: '0', supportingUah: '0' });
    expect(chart.byCategory).toEqual([
      { category: 'coin_purchase', count: 4, totalUah: '10570' },
      { category: 'delivery', count: 4, totalUah: '480' },
    ]);
  });

  it('uses inclusive daily boundaries and the backend 31-day threshold', () => {
    expect(expenseDemoChart('2025-06-08', '2025-06-08').byPeriod).toEqual([
      { period: '2025-06-08', coinsUah: '4450', supportingUah: '80' },
    ]);
    expect(expenseDemoChart('2025-05-30', '2025-06-30').granularity).toBe('day');
    expect(expenseDemoChart('2025-05-29', '2025-06-30').granularity).toBe('month');
    expect(expenseDemoChart('2025-03-13', '2025-06-07').byCategory[0]?.totalUah).toBe('1920');
  });

  it('handles empty and reversed dates', () => {
    expect(expenseDemoChart('', '2025-06-30').byPeriod).toEqual([]);
    expect(expenseDemoChart('2025-06-30', '2025-01-01').byPeriod).toEqual([]);
  });
});
