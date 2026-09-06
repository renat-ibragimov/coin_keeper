import { useQuery } from '@tanstack/react-query';
import type { TFunction } from 'i18next';
import { useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';

import { ApiError } from '@/shared/api/client';
import type { CatalogCard } from '@/shared/api/types';
import { imageSources } from '@/shared/lib/coinImage';
import { coinTitle, showsOriginal } from '@/shared/lib/coinTitle';
import { formatDate, formatSignedPercent, formatSignedUah, formatUah } from '@/shared/lib/format';
import { languageName } from '@/shared/lib/languageName';
import { priceSourceLabel } from '@/shared/lib/priceSource';
import {
  Badge,
  Button,
  Card,
  CoinImage,
  ErrorState,
  Lightbox,
  PropertyList,
  Skeleton,
  Tabs,
} from '@/shared/ui';
import type { PropertyRow, TabOption } from '@/shared/ui';

import { fetchCard, fetchOwnInstances, fetchPrices } from '../api';
import type { ChartPoint } from './chartData';
import { toChartPoints } from './chartData';
import { InstancesList } from './InstancesList';
import { PriceHistoryChart } from './PriceHistoryChart';
import { catalogSpecRows, identitySpecRows, issueSpecRows, technicalSpecRows } from './specs';
import styles from './CoinCardPage.module.css';

type PanelTab = 'specs' | 'instances' | 'prices';

export function CoinCardPage() {
  const { t } = useTranslation();
  const { id } = useParams();
  const itemId = Number.parseInt(id ?? '', 10);
  const validId = Number.isFinite(itemId) && itemId > 0;

  const cardQuery = useQuery({
    queryKey: ['catalog', 'card', itemId],
    queryFn: () => fetchCard(itemId),
    enabled: validId,
  });
  const notFound =
    !validId || (cardQuery.error instanceof ApiError && cardQuery.error.status === 404);

  if (notFound) {
    return (
      <ErrorState
        title={t('card.notFoundTitle')}
        detail={t('card.notFoundText')}
        actions={
          <Link to="/catalog">
            <Button variant="secondary">{t('common.backToCatalog')}</Button>
          </Link>
        }
      />
    );
  }
  if (cardQuery.isError) {
    return (
      <ErrorState
        detail={
          cardQuery.error instanceof ApiError && cardQuery.error.status === 0
            ? t('errors.network')
            : undefined
        }
        onRetry={() => void cardQuery.refetch()}
      />
    );
  }
  if (cardQuery.isPending) return <CardSkeleton />;
  return <CardBody card={cardQuery.data} />;
}

function CardBody({ card }: { card: CatalogCard }) {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;
  const navigate = useNavigate();
  const location = useLocation();
  const [enlarged, setEnlarged] = useState<'obverse' | 'reverse' | null>(null);
  const [tab, setTab] = useState<PanelTab>('specs');
  const instancesDisclosureRef = useRef<HTMLDetailsElement>(null);

  const pricesQuery = useQuery({
    queryKey: ['catalog', 'prices', card.id],
    queryFn: () => fetchPrices(card.id),
  });
  const instancesQuery = useQuery({
    queryKey: ['catalog', 'instances', card.id],
    queryFn: () => fetchOwnInstances(card.id),
  });

  const title = coinTitle(card, locale);
  const addUrl = `/collection/coins/new?catalogItemId=${card.id}`;
  const addState = { from: `/catalog/${card.id}` };

  const sides = [
    { key: 'obverse' as const, image: card.obverseImage, label: t('card.obverse') },
    { key: 'reverse' as const, image: card.reverseImage, label: t('card.reverse') },
  ].map((side) => ({
    ...side,
    // The card shows the medium file and the lightbox the large one.
    card: imageSources(side.image, 'card'),
    full: imageSources(side.image, 'lightbox'),
  }));
  const enlargedSide = sides.find((side) => side.key === enlarged);

  // The catalog keeps its filters in the URL, so going back through history
  // restores the exact listing; a direct link has nowhere to go but the catalog.
  const goBack = () => {
    if (location.key !== 'default') navigate(-1);
    else navigate('/catalog');
  };

  const priceItems = pricesQuery.data ?? [];
  const chartPoints = toChartPoints(priceItems);
  const hasInstances = (instancesQuery.data?.length ?? 0) > 0;
  const owned = card.quantityOwned > 0;
  // No instances of a coin the visitor doesn't have — the tab has nothing to show.
  const panelTabs: TabOption<PanelTab>[] = [
    { value: 'specs', label: t('card.specs') },
    { value: 'prices', label: t('card.priceHistory') },
    ...(owned ? [{ value: 'instances' as const, label: t('card.instances') }] : []),
  ];

  return (
    <div className={styles.page}>
      {card.isArchived ? (
        <div className={styles.archiveBanner} role="status">
          <strong>
            {t('card.archivedTitle')}
            {card.archiveReason ? `: ${card.archiveReason}` : ''}
          </strong>
          <span>{t('card.archivedText')}</span>
        </div>
      ) : null}

      <header className={styles.header}>
        {/* The 1fr/auto/1fr grid keeps the title centred on the page: the
            back button sits at the start of the first 1fr track without
            changing its width, so it stays as wide as the empty third
            track and the title lands exactly in the middle. */}
        <div className={styles.titleBar}>
          <Button variant="ghost" size="sm" onClick={goBack} className={styles.backButton}>
            ← {t('common.back')}
          </Button>
          <div className={styles.titleCell}>
            <h1 className={styles.title}>{title}</h1>
            {card.isOwn ? <Badge tone="accent">{t('catalog.badgeOwn')}</Badge> : null}
          </div>
        </div>
        {/* What the issuer calls the coin, when that is not what is shown. */}
        {showsOriginal(card, locale) ? (
          <p className={styles.original}>
            {t('card.originalName', {
              title: card.titleOriginal,
              language: languageName(card.originalLang, locale),
            })}
          </p>
        ) : null}
      </header>

      <div className={styles.hero}>
        {/* display:contents — groups the two photos for assistive tech
            without becoming a box of its own, so the grid still sees three
            equal-width columns rather than two. */}
        <div role="group" aria-label={t('card.photosLabel')} className={styles.photosGroup}>
          {sides.map((side) => (
            <figure key={side.key} className={styles.photo}>
              {side.card.src ? (
                <button
                  type="button"
                  className={styles.photoFrame}
                  onClick={() => setEnlarged(side.key)}
                  aria-label={`${t('card.enlarge')} — ${side.label}`}
                >
                  <CoinImage {...side.card} alt="" className={styles.photoImage} />
                  <span className={styles.photoLabel}>{side.label}</span>
                  <span className={styles.magnify} aria-hidden="true">
                    ⤢
                  </span>
                </button>
              ) : (
                <div className={styles.photoFrame}>
                  <CoinImage {...side.card} alt="" className={styles.photoImage} />
                  <span className={styles.photoLabel}>{side.label}</span>
                </div>
              )}
            </figure>
          ))}
        </div>

        <SidebarCard card={card} locale={locale} t={t} addUrl={addUrl} addState={addState} />
      </div>

      <Card className={styles.bottomCard} padded={false}>
        {/* Restyled locally via role/aria selectors (CoinCardPage.module.css)
            instead of touching the shared Tabs component used elsewhere. */}
        <div className={styles.tabsWrapper}>
          <Tabs
            aria-label={t('card.detailsTabs')}
            value={tab}
            onChange={setTab}
            options={panelTabs}
          />
        </div>
        <div className={styles.bottomPanel}>
          {tab === 'specs' ? (
            <>
              <div className={styles.specGrid}>
                <SpecGroup title={t('card.specGroupIdentity')} rows={identitySpecRows(card, t)} />
                <SpecGroup title={t('card.specGroupIssue')} rows={issueSpecRows(card, t, locale)} />
                <SpecGroup
                  title={t('card.specGroupTechnical')}
                  rows={technicalSpecRows(card, t, locale)}
                />
                <SpecGroup title={t('card.specGroupCatalog')} rows={catalogSpecRows(card, t)} />
              </div>
              {card.notes ? <p className={styles.notes}>{card.notes}</p> : null}
            </>
          ) : null}
          {tab === 'instances' ? (
            <>
              {instancesQuery.isError ? (
                <ErrorState onRetry={() => void instancesQuery.refetch()} />
              ) : hasInstances ? (
                <>
                  <InstancesSummary card={card} locale={locale} t={t} />
                  <details
                    ref={instancesDisclosureRef}
                    className={styles.instancesDisclosure}
                    onToggle={(event) => {
                      // Wait a frame so the revealed list has already been
                      // laid out — scrolling before that targets the old,
                      // collapsed height and undershoots.
                      if (event.currentTarget.open) {
                        requestAnimationFrame(() => {
                          instancesDisclosureRef.current?.scrollIntoView?.({
                            behavior: 'smooth',
                            block: 'end',
                          });
                        });
                      }
                    }}
                  >
                    <summary>
                      {t('card.showAllInstances', { count: instancesQuery.data?.length ?? 0 })}
                    </summary>
                    <InstancesList
                      items={instancesQuery.data}
                      loading={instancesQuery.isPending}
                      addHref={addUrl}
                    />
                  </details>
                </>
              ) : (
                <InstancesList
                  items={instancesQuery.data}
                  loading={instancesQuery.isPending}
                  addHref={addUrl}
                />
              )}
            </>
          ) : null}
          {tab === 'prices' ? (
            <>
              {pricesQuery.isPending ? <Skeleton height={180} /> : null}
              {pricesQuery.isError ? (
                <ErrorState onRetry={() => void pricesQuery.refetch()} />
              ) : null}
              {pricesQuery.data && chartPoints.length === 0 ? (
                <p className={styles.muted}>{t('card.pricesEmpty')}</p>
              ) : null}
              {chartPoints.length === 1 ? (
                <SinglePricePoint point={chartPoints[0]!} locale={locale} t={t} />
              ) : null}
              {chartPoints.length >= 2 ? <PriceHistoryChart items={priceItems} /> : null}
            </>
          ) : null}
        </div>
      </Card>

      <Lightbox
        open={enlargedSide !== undefined}
        onClose={() => setEnlarged(null)}
        label={`${enlargedSide?.label ?? ''} — ${title}`}
      >
        <CoinImage
          src={enlargedSide?.full.src}
          alt={`${enlargedSide?.label ?? ''} — ${title}`}
          className={styles.lightboxImage}
        />
      </Lightbox>
    </div>
  );
}

function SpecGroup({ title, rows }: { title: string; rows: PropertyRow[] }) {
  const hasContent = rows.some(
    (row) => row.value !== null && row.value !== undefined && row.value !== '',
  );
  if (!hasContent) return null;
  return (
    <div className={styles.specGroup}>
      <h3 className={styles.specGroupTitle}>{title}</h3>
      <PropertyList rows={rows} />
    </div>
  );
}

interface SidebarCardProps {
  card: CatalogCard;
  locale: string;
  t: TFunction;
  addUrl: string;
  addState: { from: string };
}

/**
 * The sidebar answers one question only — "do I have it, and what does it
 * cost right now?". Purchase price, valuation and profit are the visitor's
 * own numbers, not the coin's, so they live on the "Мої екземпляри" tab
 * instead (InstancesSummary below).
 */
function SidebarCard({ card, locale, t, addUrl, addState }: SidebarCardProps) {
  const owned = card.quantityOwned > 0;
  const sourceLabel = priceSourceLabel(card.priceSource, t);
  const observedDate = formatDate(card.priceObservedAt, locale);
  const openLabel = sourceLabel
    ? t('card.openOnSource', { source: sourceLabel })
    : t('catalog.sourceLink');

  return (
    <Card className={styles.sidebarCard} padded={false}>
      <h2 className={[styles.statusHeading, owned ? styles.statusOwned : ''].join(' ')}>
        {owned ? t('card.inCollection') : t('card.notInCollection')}
      </h2>
      {owned ? (
        <p className={styles.quantityLine}>
          {t('card.quantity')}:{' '}
          <strong className="tabular">{t('card.pieces', { count: card.quantityOwned })}</strong>
        </p>
      ) : null}

      <div className={styles.priceBlock}>
        <span className={styles.priceLabel}>{t('card.currentPrice')}</span>
        {card.marketPriceUah !== null ? (
          <>
            <p className={styles.priceValue}>{formatUah(card.marketPriceUah, locale)}</p>
            {sourceLabel || observedDate ? (
              <p className={styles.priceMeta}>
                {sourceLabel ? t('card.priceSource', { source: sourceLabel }) : null}
                {sourceLabel && observedDate ? ' · ' : null}
                {observedDate ? t('card.priceUpdated', { date: observedDate }) : null}
              </p>
            ) : null}
          </>
        ) : (
          <p className={styles.muted}>{t('card.priceEmpty')}</p>
        )}
      </div>

      <div className={styles.cardActions}>
        <Link to={addUrl} state={addState}>
          <Button block>
            {owned ? t('catalog.addAnotherCopy') : `+ ${t('catalog.addToCollection')}`}
          </Button>
        </Link>
      </div>

      {card.sourceUrl ? (
        <a className={styles.sourceLink} href={card.sourceUrl} target="_blank" rel="noreferrer">
          {openLabel} ↗
        </a>
      ) : null}
    </Card>
  );
}

/**
 * Summary at the top of "Мої екземпляри": the visitor's own purchase and
 * valuation numbers, aggregated across every instance of this coin they own.
 */
function InstancesSummary({
  card,
  locale,
  t,
}: {
  card: CatalogCard;
  locale: string;
  t: TFunction;
}) {
  const currentValue =
    card.marketPriceUah !== null ? Number(card.marketPriceUah) * card.quantityOwned : null;
  const purchaseTotal = Number(card.purchaseTotalUah);
  const change = currentValue !== null ? currentValue - purchaseTotal : null;
  const changePercent =
    change !== null && purchaseTotal > 0 ? (change / purchaseTotal) * 100 : null;

  const rows: (PropertyRow | null)[] = [
    {
      key: 'quantity',
      label: t('card.quantity'),
      value: <span className="tabular">{t('card.pieces', { count: card.quantityOwned })}</span>,
    },
    {
      key: 'purchaseTotal',
      label: t('card.purchasedTotal'),
      value: <span className="tabular">{formatUah(card.purchaseTotalUah, locale)}</span>,
    },
    {
      key: 'currentValue',
      label: t('card.currentValue'),
      value:
        currentValue !== null ? (
          <span className="tabular">{formatUah(currentValue, locale)}</span>
        ) : (
          <span className={styles.muted}>{t('catalog.noPrice')}</span>
        ),
    },
    change !== null
      ? {
          key: 'change',
          label: t('card.valueChange'),
          value: (
            <span
              className={[
                'tabular',
                change > 0 ? styles.positive : change < 0 ? styles.negative : '',
              ].join(' ')}
            >
              {formatSignedUah(change, locale)}
              {changePercent !== null ? (
                <span className={styles.changePercent}>
                  {' '}
                  ({formatSignedPercent(changePercent, locale)})
                </span>
              ) : null}
            </span>
          ),
        }
      : null,
  ];

  return (
    <PropertyList
      className={styles.instancesSummary}
      rows={rows.filter((row): row is PropertyRow => row !== null)}
    />
  );
}

function SinglePricePoint({
  point,
  locale,
  t,
}: {
  point: ChartPoint;
  locale: string;
  t: TFunction;
}) {
  return (
    <div className={styles.singlePrice}>
      <p className={styles.priceValue}>{formatUah(point.value, locale)}</p>
      <p className={styles.priceMeta}>
        {formatDate(point.source.observedAt, locale)} · {priceSourceLabel(point.source.source, t)}
      </p>
    </div>
  );
}

function CardSkeleton() {
  return (
    <div className={styles.page} aria-busy="true">
      <Skeleton width={320} height={32} style={{ margin: '0 auto' }} />
      <div className={styles.hero}>
        <Skeleton height={340} />
        <Skeleton height={340} />
        <Skeleton height={340} />
      </div>
      <Skeleton height={220} />
      <Skeleton height={240} />
    </div>
  );
}
