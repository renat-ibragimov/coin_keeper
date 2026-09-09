import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';
import type { TooltipContentProps } from 'recharts';
import { useTranslation } from 'react-i18next';

import type { ExpenseCategorySummary } from '@/shared/api/types';
import { formatPercent, formatUah } from '@/shared/lib/format';
import type { ChartPalette } from '@/shared/theme/useChartPalette';

import styles from './ChartTooltip.module.css';
import donutStyles from './ExpensesByCategoryChart.module.css';

interface Props {
  data: ExpenseCategorySummary[];
  locale: string;
  palette: ChartPalette;
}

/** Darkest slice for the largest category, lightening down the ranked list. */
function shareFor(index: number, count: number): number {
  if (count <= 1) return 0.9;
  const min = 0.32;
  const max = 0.92;
  return max - (index / (count - 1)) * (max - min);
}

export function ExpensesByCategoryChart({ data, locale, palette }: Props) {
  const { t } = useTranslation();
  const total = data.reduce((sum, row) => sum + Number(row.totalUah), 0);
  const colors = data.map((_, index) => palette.shade(shareFor(index, data.length)));

  const chartData = data.map((row) => ({
    category: row.category,
    value: Number(row.totalUah),
    label: t(`expenses.categories.${row.category}`),
  }));

  return (
    <div className={donutStyles.layout}>
      <ResponsiveContainer width={200} height={200} className={donutStyles.chart}>
        <PieChart>
          <Pie
            data={chartData}
            dataKey="value"
            nameKey="label"
            innerRadius={56}
            outerRadius={86}
            paddingAngle={data.length > 1 ? 2 : 0}
            stroke={palette.panel}
            strokeWidth={2}
          >
            {chartData.map((row, index) => (
              <Cell key={row.category} fill={colors[index]} />
            ))}
          </Pie>
          {/* Glued to the cursor: recharts otherwise glides the box to its new
              place over 400ms, and flips it to the other side of the cursor once
              it would cross the plot's edge — a ~150px jump upwards as the
              pointer moves down, since the box is half as tall as the chart. No
              animation and a free vertical axis mean it simply trails the
              pointer; near the bottom it hangs over the axis instead of jumping
              (docs/08-ui-map.md). */}
          <Tooltip
            isAnimationActive={false}
            allowEscapeViewBox={{ x: false, y: true }}
            /* Over the legend list below the chart, same as the month chart. */
            wrapperStyle={{ zIndex: 1 }}
            content={(props: TooltipContentProps) => {
              const row = props.active ? props.payload?.[0] : undefined;
              if (!row) return null;
              const value = Number(row.value ?? 0);
              return (
                <div className={styles.tooltip}>
                  <div className={styles.title}>{row.name}</div>
                  <div className={styles.row}>
                    <span className={styles.label}>{formatUah(value, locale)}</span>
                    <span className={styles.value}>
                      {formatPercent(total > 0 ? (value / total) * 100 : 0, locale, 1)}
                    </span>
                  </div>
                </div>
              );
            }}
          />
        </PieChart>
      </ResponsiveContainer>
      <ul className={donutStyles.legend}>
        {chartData.map((row, index) => (
          <li key={row.category} className={donutStyles.legendRow}>
            <span className={donutStyles.swatch} style={{ background: colors[index] }} />
            <span className={donutStyles.legendLabel}>{row.label}</span>
            <span className={donutStyles.legendValue}>{formatUah(row.value, locale)}</span>
            <span className={donutStyles.legendShare}>
              {formatPercent(total > 0 ? (row.value / total) * 100 : 0, locale, 0)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
