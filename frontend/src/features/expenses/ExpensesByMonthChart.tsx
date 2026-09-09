import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { TooltipContentProps } from 'recharts';
import { useTranslation } from 'react-i18next';

import type { ExpenseMonthTotal } from '@/shared/api/types';
import { formatMonthShort, formatMonthYear, formatUah } from '@/shared/lib/format';
import type { ChartPalette } from '@/shared/theme/useChartPalette';

import styles from './ChartTooltip.module.css';

interface Props {
  data: ExpenseMonthTotal[];
  locale: string;
  palette: ChartPalette;
}

function MonthTooltip({
  active,
  payload,
  label,
  locale,
  palette,
  coinsLabel,
  supportingLabel,
  totalLabel,
}: TooltipContentProps & {
  locale: string;
  palette: ChartPalette;
  coinsLabel: string;
  supportingLabel: string;
  totalLabel: string;
}) {
  if (!active || !payload || payload.length === 0) return null;
  const coins = Number(payload.find((row) => row.dataKey === 'coinsUah')?.value ?? 0);
  const supporting = Number(payload.find((row) => row.dataKey === 'supportingUah')?.value ?? 0);
  return (
    <div className={styles.tooltip}>
      <div className={styles.title}>
        {typeof label === 'string' ? formatMonthYear(`${label}-01`, locale) : label}
      </div>
      <div className={styles.row}>
        <span className={styles.swatch} style={{ background: palette.series1 }} />
        <span className={styles.label}>{coinsLabel}</span>
        <span className={styles.value}>{formatUah(coins, locale)}</span>
      </div>
      <div className={styles.row}>
        <span className={styles.swatch} style={{ background: palette.series2 }} />
        <span className={styles.label}>{supportingLabel}</span>
        <span className={styles.value}>{formatUah(supporting, locale)}</span>
      </div>
      <div className={styles.total}>
        <span>{totalLabel}</span>
        <span>{formatUah(coins + supporting, locale)}</span>
      </div>
    </div>
  );
}

export function ExpensesByMonthChart({ data, locale, palette }: Props) {
  const { t } = useTranslation();
  const coinsLabel = t('expenses.chartCoins');
  const supportingLabel = t('expenses.chartSupporting');
  const totalLabel = t('expenses.chartTotal');
  const chartData = data.map((row) => ({
    ...row,
    coinsUah: Number(row.coinsUah),
    supportingUah: Number(row.supportingUah),
  }));

  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid stroke={palette.grid} strokeDasharray="3 3" vertical={false} />
        <XAxis
          dataKey="month"
          tickFormatter={(value: string) => formatMonthShort(value, locale)}
          tick={{ fill: palette.axis, fontSize: 12 }}
          axisLine={{ stroke: palette.grid }}
          tickLine={false}
        />
        <YAxis
          tick={{ fill: palette.axis, fontSize: 12 }}
          axisLine={false}
          tickLine={false}
          width={48}
        />
        {/* Glued to the cursor: recharts otherwise glides the box to its new
            place over 400ms, and flips it to the other side of the cursor once
            it would cross the plot's edge — a ~150px jump upwards as the
            pointer moves down, since the box is half as tall as the chart. No
            animation and a free vertical axis mean it simply trails the
            pointer; near the bottom it hangs over the axis instead of jumping
            (docs/08-ui-map.md). */}
        <Tooltip
          cursor={{ fill: palette.grid, opacity: 0.25 }}
          isAnimationActive={false}
          allowEscapeViewBox={{ x: false, y: true }}
          /* The legend's wrapper is positioned too and comes later in the DOM,
             so without this the box slides under its labels on the way down.
             wrapperStyle is merged last, over recharts' own positioning. */
          wrapperStyle={{ zIndex: 1 }}
          content={(props) => (
            <MonthTooltip
              {...props}
              locale={locale}
              palette={palette}
              coinsLabel={coinsLabel}
              supportingLabel={supportingLabel}
              totalLabel={totalLabel}
            />
          )}
        />
        <Legend
          wrapperStyle={{ fontSize: 12.5, color: palette.axis }}
          formatter={(value) => (value === 'coinsUah' ? coinsLabel : supportingLabel)}
        />
        <Bar
          dataKey="coinsUah"
          stackId="month"
          fill={palette.series1}
          radius={[0, 0, 4, 4]}
          stroke={palette.panel}
          strokeWidth={2}
        />
        <Bar
          dataKey="supportingUah"
          stackId="month"
          fill={palette.series2}
          radius={[4, 4, 0, 0]}
          stroke={palette.panel}
          strokeWidth={2}
        />
      </BarChart>
    </ResponsiveContainer>
  );
}
