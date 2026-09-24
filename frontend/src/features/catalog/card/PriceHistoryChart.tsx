import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  AreaSeries,
  ColorType,
  CrosshairMode,
  LineStyle,
  createChart,
  createSeriesMarkers,
} from 'lightweight-charts';
import type {
  IChartApi,
  MouseEventParams,
  SeriesMarker,
  Time,
  UTCTimestamp,
} from 'lightweight-charts';

import type { PriceHistoryItem } from '@/shared/api/types';
import { formatDate, formatUah } from '@/shared/lib/format';
import { priceSourceLabel } from '@/shared/lib/priceSource';
import { useChartPalette } from '@/shared/theme/useChartPalette';
import { Tabs } from '@/shared/ui';
import type { TabOption } from '@/shared/ui';
import tooltipStyles from '@/shared/ui/ChartTooltip.module.css';

import { toChartPoints } from './chartData';
import { buildPriceSeries, rangeStart } from './priceChartData';
import type { RangePreset } from './priceChartData';

import styles from './PriceHistoryChart.module.css';

const HEIGHT = 260;

interface Tooltip {
  x: number;
  y: number;
  /** True once the cursor is past the chart's midpoint, so the box opens to the left instead of covering the price scale. */
  flip: boolean;
  date: string;
  value: string;
  tags: string[];
}

/**
 * Price history on an interactive lightweight-charts area series: mouse-wheel
 * zoom and drag-to-pan come from the library for free, plus a quick-range
 * strip (1М/6М/1Р/Усі). Suspect snapshots are excluded from the plotted line
 * and the price scale's autoscale (docs/integrations.md) — one bad price
 * used to stretch the whole axis and flatten the real trend into a "worm" —
 * and shown instead as a separate, differently-coloured marker.
 */
export function PriceHistoryChart({ items }: { items: PriceHistoryItem[] }) {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;
  const palette = useChartPalette();
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const [range, setRange] = useState<RangePreset>('all');
  const [tooltip, setTooltip] = useState<Tooltip | null>(null);

  const points = useMemo(() => toChartPoints(items), [items]);
  const { series: seriesData, markers: markerPoints } = useMemo(
    () => buildPriceSeries(points),
    [points],
  );
  const pointsById = useMemo(
    () => new Map(points.map((point) => [point.source.id, point])),
    [points],
  );
  const timeToSourceId = useMemo(
    () => new Map(seriesData.map((point) => [point.time, point.sourceId])),
    [seriesData],
  );
  const latest = seriesData.length ? seriesData[seriesData.length - 1]!.time : null;
  const earliest = seriesData.length ? seriesData[0]!.time : null;

  const rangeOptions: TabOption<RangePreset>[] = [
    { value: '1m', label: t('card.chartRange1m') },
    { value: '6m', label: t('card.chartRange6m') },
    { value: '1y', label: t('card.chartRange1y') },
    { value: 'all', label: t('card.chartRangeAll') },
  ];

  useEffect(() => {
    const container = containerRef.current;
    if (!container || points.length === 0) return;

    const chart = createChart(container, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: palette.axis,
        fontFamily: "'Source Sans 3', 'Segoe UI', system-ui, sans-serif",
        fontSize: 12,
      },
      grid: {
        vertLines: { visible: false },
        horzLines: { color: palette.grid, style: LineStyle.Dotted },
      },
      crosshair: {
        mode: CrosshairMode.Magnet,
        vertLine: { color: palette.grid, labelBackgroundColor: palette.tooltipBg },
        horzLine: { color: palette.grid, labelBackgroundColor: palette.tooltipBg },
      },
      rightPriceScale: { borderColor: palette.grid },
      timeScale: { borderColor: palette.grid, timeVisible: false },
      localization: { locale: locale === 'uk' ? 'uk-UA' : 'en-GB' },
    });

    const series = chart.addSeries(AreaSeries, {
      lineColor: palette.series1,
      topColor: palette.shade(0.35),
      bottomColor: palette.shade(0),
      lineWidth: 2,
      priceLineVisible: false,
      crosshairMarkerRadius: 5,
      crosshairMarkerBorderColor: palette.panel,
      crosshairMarkerBackgroundColor: palette.series1,
    });
    series.setData(
      seriesData.map((point) => ({ time: point.time as UTCTimestamp, value: point.value })),
    );

    const markerList: SeriesMarker<Time>[] = markerPoints.map((marker) => {
      const time = marker.time as UTCTimestamp;
      if (marker.kind === 'own') {
        return {
          time,
          position: 'inBar',
          shape: 'circle',
          color: palette.accent,
          id: String(marker.sourceId),
          size: 1.4,
        };
      }
      return {
        time,
        position: 'atPriceMiddle',
        price: marker.value,
        shape: 'circle',
        color: palette.danger,
        id: String(marker.sourceId),
        size: 1,
      };
    });
    createSeriesMarkers(series, markerList, { autoScale: false });

    chart.timeScale().fitContent();

    const handleCrosshairMove = (param: MouseEventParams<Time>) => {
      const point = param.point;
      const objectId = param.hoveredInfo?.objectId;
      const hovered =
        typeof objectId === 'string'
          ? pointsById.get(Number(objectId))
          : typeof param.time === 'number'
            ? pointsById.get(timeToSourceId.get(param.time) ?? -1)
            : undefined;
      if (!point || !hovered) {
        setTooltip(null);
        return;
      }
      const tags = [
        priceSourceLabel(hovered.source.source, t),
        hovered.source.grade,
        hovered.source.isOwn ? t('card.legendOwn') : null,
        hovered.source.isSuspect ? t('card.legendSuspect') : null,
      ].filter((tag): tag is string => Boolean(tag));
      setTooltip({
        x: point.x,
        y: point.y,
        flip: point.x > container.clientWidth / 2,
        date: formatDate(hovered.source.observedAt, locale) ?? '',
        value: formatUah(hovered.value, locale) ?? '',
        tags,
      });
    };
    chart.subscribeCrosshairMove(handleCrosshairMove);
    chartRef.current = chart;

    return () => {
      chart.unsubscribeCrosshairMove(handleCrosshairMove);
      chart.remove();
      chartRef.current = null;
      setTooltip(null);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seriesData, markerPoints, palette, locale]);

  if (points.length === 0) {
    return <p className={styles.empty}>{t('card.pricesEmpty')}</p>;
  }

  const first = points[0]!;
  const last = points[points.length - 1]!;

  return (
    <figure className={styles.figure}>
      <div className={styles.toolbar}>
        <Tabs
          options={rangeOptions}
          value={range}
          aria-label={t('card.chartRangeLabel')}
          onChange={(preset) => {
            setRange(preset);
            const chart = chartRef.current;
            if (!chart || latest === null || earliest === null) return;
            if (preset === 'all') {
              chart.timeScale().fitContent();
              return;
            }
            const from = Math.max(rangeStart(latest, preset), earliest);
            chart
              .timeScale()
              .setVisibleRange({ from: from as UTCTimestamp, to: latest as UTCTimestamp });
          }}
        />
      </div>
      <div className={styles.chartWrap}>
        <div
          ref={containerRef}
          className={styles.chart}
          style={{ height: HEIGHT }}
          role="img"
          aria-label={t('card.chartLabel', {
            count: points.length,
            from: formatDate(first.source.observedAt, locale),
            to: formatDate(last.source.observedAt, locale),
          })}
        />
        {tooltip ? (
          <div
            className={tooltipStyles.tooltip}
            style={{
              position: 'absolute',
              zIndex: 5,
              pointerEvents: 'none',
              left: tooltip.x,
              top: tooltip.y,
              transform: tooltip.flip ? 'translate(calc(-100% - 12px), 0)' : 'translate(12px, 0)',
            }}
          >
            <div className={tooltipStyles.title}>{tooltip.date}</div>
            <div className={tooltipStyles.row}>
              <span className={tooltipStyles.value}>{tooltip.value}</span>
            </div>
            {tooltip.tags.length > 0 ? (
              <div className={styles.tooltipTags}>{tooltip.tags.join(' · ')}</div>
            ) : null}
          </div>
        ) : null}
      </div>
      <div className={styles.legend}>
        <span className={styles.legendItem}>
          <span className={styles.legendLine} style={{ background: palette.series1 }} />
          {t('card.legendPrice')}
        </span>
        {markerPoints.some((marker) => marker.kind === 'own') ? (
          <span className={styles.legendItem}>
            <span className={styles.legendDot} style={{ background: palette.accent }} />
            {t('card.legendOwn')}
          </span>
        ) : null}
        {markerPoints.some((marker) => marker.kind === 'suspect') ? (
          <span className={styles.legendItem}>
            <span className={styles.legendDot} style={{ background: palette.danger }} />
            {t('card.legendSuspect')}
          </span>
        ) : null}
      </div>
    </figure>
  );
}
