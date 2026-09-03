import { useTranslation } from 'react-i18next';

import type { PriceHistoryItem } from '@/shared/api/types';
import { formatDate, formatMonthYear, formatNumber } from '@/shared/lib/format';

import { toChartPoints } from './chartData';

import styles from './PriceHistoryChart.module.css';

const WIDTH = 640;
const HEIGHT = 220;
const PAD = { top: 14, right: 18, bottom: 30, left: 56 };
const Y_TICKS = 4;

/** A round upper bound so the grid lands on readable numbers. */
function niceCeiling(max: number): number {
  if (max <= 0) return 1;
  const magnitude = 10 ** Math.floor(Math.log10(max));
  const normalised = max / magnitude;
  const step = normalised <= 1 ? 1 : normalised <= 2 ? 2 : normalised <= 5 ? 5 : 10;
  return step * magnitude;
}

/**
 * Price history as a plain SVG line: one series, the visible snapshots.
 *
 * Suspect snapshots (failed validation, docs/05-integrations.md) stay on the
 * chart so the record is honest, but they are drawn as hollow markers and are
 * never joined into the trend line. The user's own snapshots get a distinct
 * marker: they count in their valuation and nobody else's.
 */
export function PriceHistoryChart({ items }: { items: PriceHistoryItem[] }) {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;
  const points = toChartPoints(items);

  if (points.length === 0) {
    return <p className={styles.empty}>{t('card.pricesEmpty')}</p>;
  }

  const first = points[0]!;
  const last = points[points.length - 1]!;
  const timeMin = first.time;
  const timeMax = last.time;
  const yMax = niceCeiling(Math.max(...points.map((point) => point.value)));
  const plotWidth = WIDTH - PAD.left - PAD.right;
  const plotHeight = HEIGHT - PAD.top - PAD.bottom;

  const x = (time: number) =>
    timeMax === timeMin
      ? PAD.left + plotWidth / 2
      : PAD.left + ((time - timeMin) / (timeMax - timeMin)) * plotWidth;
  const y = (value: number) => PAD.top + plotHeight - (value / yMax) * plotHeight;

  const trend = points.filter((point) => !point.source.isSuspect);
  const trendPath = trend
    .map((point, index) => `${index ? 'L' : 'M'}${x(point.time)},${y(point.value)}`)
    .join(' ');
  const areaPath =
    trend.length > 1 ? `${trendPath} L${x(last.time)},${y(0)} L${x(trend[0]!.time)},${y(0)} Z` : '';

  const yTicks = Array.from({ length: Y_TICKS + 1 }, (_, index) => (yMax / Y_TICKS) * index);
  const xLabelCount = Math.min(5, Math.max(2, points.length));
  const xTicks =
    timeMax === timeMin
      ? [timeMin]
      : Array.from(
          { length: xLabelCount },
          (_, index) => timeMin + ((timeMax - timeMin) / (xLabelCount - 1)) * index,
        );

  const hasOwn = points.some((point) => point.source.isOwn);
  const hasSuspect = points.some((point) => point.source.isSuspect);

  return (
    <figure className={styles.figure}>
      <svg
        className={styles.chart}
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label={t('card.chartLabel', {
          count: points.length,
          from: formatDate(first.source.observedAt, locale),
          to: formatDate(last.source.observedAt, locale),
        })}
      >
        {yTicks.map((tick) => (
          <g key={tick}>
            <line
              className={styles.grid}
              x1={PAD.left}
              x2={WIDTH - PAD.right}
              y1={y(tick)}
              y2={y(tick)}
            />
            <text className={styles.axisLabel} x={PAD.left - 8} y={y(tick) + 4} textAnchor="end">
              {formatNumber(tick, locale, 0)}
            </text>
          </g>
        ))}
        {xTicks.map((tick) => (
          <text
            key={tick}
            className={styles.axisLabel}
            x={x(tick)}
            y={HEIGHT - 8}
            textAnchor="middle"
          >
            {formatMonthYear(new Date(tick), locale)}
          </text>
        ))}

        {areaPath ? <path className={styles.area} d={areaPath} /> : null}
        {trend.length > 1 ? (
          <path className={styles.line} d={trendPath} data-testid="trend-line" />
        ) : null}

        {points.map((point) => {
          const label = [
            formatDate(point.source.observedAt, locale),
            `${formatNumber(point.value, locale)} ₴`,
            point.source.source,
            point.source.grade,
            point.source.isOwn ? t('card.legendOwn') : null,
            point.source.isSuspect ? t('card.legendSuspect') : null,
          ]
            .filter(Boolean)
            .join(' · ');
          const cx = x(point.time);
          const cy = y(point.value);
          if (point.source.isSuspect) {
            return (
              <g key={point.source.id} data-testid="suspect-point">
                <title>{label}</title>
                <circle className={styles.suspect} cx={cx} cy={cy} r={5} />
                <path
                  className={styles.suspectCross}
                  d={`M${cx - 2.5},${cy - 2.5} L${cx + 2.5},${cy + 2.5} M${cx + 2.5},${cy - 2.5} L${cx - 2.5},${cy + 2.5}`}
                />
              </g>
            );
          }
          return (
            <g key={point.source.id} data-testid={point.source.isOwn ? 'own-point' : 'point'}>
              <title>{label}</title>
              <circle
                className={point.source.isOwn ? styles.ownPoint : styles.point}
                cx={cx}
                cy={cy}
                r={point.source.isOwn ? 5 : 3.5}
              />
            </g>
          );
        })}
      </svg>
      <figcaption className={styles.legend}>
        <span>
          <i className={`${styles.swatch} ${styles.swatchTrend}`} aria-hidden="true" />
          {t('card.legendTrend')}
        </span>
        {hasOwn ? (
          <span>
            <i className={`${styles.swatch} ${styles.swatchOwn}`} aria-hidden="true" />
            {t('card.legendOwn')}
          </span>
        ) : null}
        {hasSuspect ? (
          <span>
            <i className={`${styles.swatch} ${styles.swatchSuspect}`} aria-hidden="true" />
            {t('card.legendSuspect')}
          </span>
        ) : null}
      </figcaption>
    </figure>
  );
}
