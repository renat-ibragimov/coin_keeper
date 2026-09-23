import type { ExpensesChart } from '@/shared/api/types';

// The same four purchases as the collection preview, in a June 2025 snapshot.
export const expenseDemoToday = new Date(2025, 5, 30);
const purchases = [
  { date: '2025-06-08', coin: 0, price: 4450, delivery: 80 },
  { date: '2025-05-20', coin: 1, price: 220, delivery: 30 },
  { date: '2025-04-12', coin: 2, price: 1700, delivery: 250 },
  { date: '2025-03-12', coin: 0, price: 4200, delivery: 120 },
];
export const expenseDemoRows = purchases.flatMap((purchase) => [
  {
    date: purchase.date,
    coin: purchase.coin,
    category: 'coin_purchase' as const,
    amount: purchase.price,
  },
  {
    date: purchase.date,
    coin: purchase.coin,
    category: 'delivery' as const,
    amount: purchase.delivery,
  },
]);

export function expenseDemoChart(dateFrom: string, dateTo: string): ExpensesChart {
  const start = new Date(`${dateFrom}T00:00:00Z`);
  const end = new Date(`${dateTo}T00:00:00Z`);
  const days = (end.getTime() - start.getTime()) / 86400000;
  const granularity = days <= 31 ? 'day' : 'month';
  const empty = { granularity, byPeriod: [], byCategory: [] } satisfies ExpensesChart;
  if (!Number.isFinite(days) || days < 0) return empty;
  const rows = expenseDemoRows.filter((row) => row.date >= dateFrom && row.date <= dateTo);
  // Match the backend's inclusive, zero-filled daily/monthly buckets.
  const cursor = new Date(start);
  if (granularity === 'month') cursor.setUTCDate(1);
  const byPeriod: ExpensesChart['byPeriod'] = [];
  while (cursor <= end) {
    const period = cursor.toISOString().slice(0, granularity === 'day' ? 10 : 7);
    const bucket = rows.filter((row) => row.date.startsWith(period));
    byPeriod.push({
      period,
      coinsUah: String(
        bucket
          .filter((row) => row.category === 'coin_purchase')
          .reduce((sum, row) => sum + row.amount, 0),
      ),
      supportingUah: String(
        bucket
          .filter((row) => row.category !== 'coin_purchase')
          .reduce((sum, row) => sum + row.amount, 0),
      ),
    });
    if (granularity === 'day') cursor.setUTCDate(cursor.getUTCDate() + 1);
    else cursor.setUTCMonth(cursor.getUTCMonth() + 1);
  }
  const byCategory = (['coin_purchase', 'delivery'] as const).flatMap((category) => {
    const selected = rows.filter((row) => row.category === category);
    return selected.length
      ? [
          {
            category,
            count: selected.length,
            totalUah: String(selected.reduce((sum, row) => sum + row.amount, 0)),
          },
        ]
      : [];
  });
  return { granularity, byPeriod, byCategory };
}
