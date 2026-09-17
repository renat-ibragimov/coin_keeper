import { useQuery } from '@tanstack/react-query';
import type { TFunction } from 'i18next';
import { ArrowLeft, CircleCheck, CircleMinus, Maximize2 } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';

import { useAuth } from '@/features/auth/useAuth';
import { GuestAddButton } from '../GuestAddButton';
import { fetchBootstrap } from '@/features/dashboard/api';
import { ApiError } from '@/shared/api/client';
import type { CatalogCard } from '@/shared/api/types';
import { imageSources } from '@/shared/lib/coinImage';
import { coinTitle, showsOriginal } from '@/shared/lib/coinTitle';
import {
  currencySymbol,
  formatDate,
  formatSignedPercent,
  formatSignedUah,
  formatUah,
} from '@/shared/lib/format';
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
} from '@/shared/ui';
import type { PropertyRow } from '@/shared/ui';

import { fetchCard, fetchOwnInstances, fetchPrices } from '../api';
import type { ChartPoint } from './chartData';
import { toChartPoints } from './chartData';
import { InstancesList } from './InstancesList';
import { PriceHistoryChart } from './PriceHistoryChart';
import type { SecondaryCurrency } from '@/shared/lib/secondaryAmount';
import {
  formatSecondary,
  formatSecondarySigned,
  pickSecondary,
  secondaryRateFrom,
  toSecondary,
} from '@/shared/lib/secondaryAmount';
import { catalogSpecRows, identitySpecRows, issueSpecRows, technicalSpecRows } from './specs';
import styles from './CoinCardPage.module.css';

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
  const { user } = useAuth();
  const locale = i18n.language;
  const navigate = useNavigate();
  const location = useLocation();
  const [enlarged, setEnlarged] = useState<'obverse' | 'reverse' | null>(null);

  const pricesQuery = useQuery({
    queryKey: ['catalog', 'prices', card.id],
    queryFn: () => fetchPrices(card.id),
    enabled: Boolean(user),
  });
  const instancesQuery = useQuery({
    queryKey: ['catalog', 'instances', card.id],
    queryFn: () => fetchOwnInstances(card.id),
    enabled: Boolean(user),
  });
  // Shares the 'bootstrap' cache key with the dashboard, so this is not a
  // second network round trip once that page has already loaded it.
  const bootstrapQuery = useQuery({
    queryKey: ['bootstrap'],
    queryFn: fetchBootstrap,
    enabled: Boolean(user),
  });
  const secondaryCurrency: SecondaryCurrency =
    bootstrapQuery.data?.settings.secondaryCurrency === 'EUR' ? 'EUR' : 'USD';
  const secondaryRate = secondaryRateFrom(bootstrapQuery.data?.exchangeRates, secondaryCurrency);

  const title = coinTitle(card, locale);
  const addUrl = `/collection/add?catalogItemId=${card.id}`;
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
  const description = card.description;
  const hasDescription = Boolean(
    description && (description.general || description.obverse || description.reverse),
  );

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
            <ArrowLeft size={15} aria-hidden="true" />
            {t('common.back')}
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
                    <Maximize2 size={18} />
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

        <SidebarCard
          card={card}
          locale={locale}
          t={t}
          addUrl={addUrl}
          addState={addState}
          secondaryCurrency={secondaryCurrency}
          secondaryRate={secondaryRate}
          guest={!user}
        />
      </div>

      {owned && hasInstances ? (
        <ValueSummary
          card={card}
          locale={locale}
          t={t}
          secondaryCurrency={secondaryCurrency}
          secondaryRate={secondaryRate}
        />
      ) : null}

      {owned ? (
        <Card className={styles.sectionCard}>
          <h2 className={`${styles.sectionTitle} ${styles.instancesHeading}`}>
            {t('card.instances')}
            {hasInstances ? <Badge>{instancesQuery.data?.length ?? 0}</Badge> : null}
          </h2>
          {instancesQuery.isError ? (
            <ErrorState onRetry={() => void instancesQuery.refetch()} />
          ) : (
            <InstancesList
              items={instancesQuery.data}
              loading={instancesQuery.isPending}
              addHref={addUrl}
              coinTitle={title}
              photo={sides[0]!.card}
              currentPriceUah={card.marketPriceUah}
              secondaryCurrency={secondaryCurrency}
              secondaryRate={secondaryRate}
            />
          )}
        </Card>
      ) : null}

      {hasDescription ? (
        <Card className={styles.sectionCard}>
          <h2 className={styles.sectionTitle}>{t('card.description')}</h2>
          <div className={styles.descriptionSides}>
            {description?.general ? (
              <div className={styles.descriptionSide}>
                <p className={styles.descriptionText}>{description.general}</p>
              </div>
            ) : null}
            {description?.obverse ? (
              <div className={styles.descriptionSide}>
                <h3 className={styles.descriptionSideTitle}>{t('card.obverse')}</h3>
                <p className={styles.descriptionText}>{description.obverse}</p>
              </div>
            ) : null}
            {description?.reverse ? (
              <div className={styles.descriptionSide}>
                <h3 className={styles.descriptionSideTitle}>{t('card.reverse')}</h3>
                <p className={styles.descriptionText}>{description.reverse}</p>
              </div>
            ) : null}
          </div>
        </Card>
      ) : null}

      <Card className={styles.sectionCard}>
        <h2 className={styles.sectionTitle}>{t('card.specs')}</h2>
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
      </Card>

      {user ? (
        <Card className={styles.sectionCard}>
          <h2 className={styles.sectionTitle}>{t('card.priceHistory')}</h2>
          {pricesQuery.isPending ? <Skeleton height={180} /> : null}
          {pricesQuery.isError ? <ErrorState onRetry={() => void pricesQuery.refetch()} /> : null}
          {pricesQuery.data && chartPoints.length === 0 ? (
            <p className={styles.muted}>{t('card.pricesEmpty')}</p>
          ) : null}
          {chartPoints.length === 1 ? (
            <SinglePricePoint point={chartPoints[0]!} locale={locale} t={t} />
          ) : null}
          {chartPoints.length >= 2 ? <PriceHistoryChart items={priceItems} /> : null}
        </Card>
      ) : null}

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
  secondaryCurrency: SecondaryCurrency;
  secondaryRate: number | null;
  guest: boolean;
}

/**
 * The sidebar answers one question only — "do I have it, and what does it
 * cost right now?". Purchase price, valuation and profit are the visitor's
 * own numbers, not the coin's, so they live in the "Мої екземпляри" section
 * instead (InstancesSummary below).
 */
function SidebarCard({
  card,
  locale,
  t,
  addUrl,
  addState,
  secondaryCurrency,
  secondaryRate,
  guest,
}: SidebarCardProps) {
  const owned = card.quantityOwned > 0;
  const sourceLabel = priceSourceLabel(card.priceSource, t);
  const observedDate = formatDate(card.priceObservedAt, locale);
  const openLabel = sourceLabel
    ? t('card.openOnSource', { source: sourceLabel })
    : t('catalog.sourceLink');
  const priceApprox =
    !guest && card.marketPriceUah != null
      ? formatSecondary(toSecondary(Number(card.marketPriceUah), secondaryRate), locale)
      : null;
  const priceApproxText =
    priceApprox !== null
      ? t('card.approxSecondary', { value: priceApprox, symbol: currencySymbol(secondaryCurrency) })
      : t('dashboard.rateMissing');

  return (
    <Card className={styles.sidebarCard} padded={false}>
      {!guest ? (
        <>
          <div className={styles.statusRow}>
            <span
              className={[
                styles.statusIcon,
                owned ? styles.statusIconOwned : styles.statusIconAbsent,
              ].join(' ')}
              aria-hidden="true"
            >
              {owned ? <CircleCheck strokeWidth={1.75} /> : <CircleMinus strokeWidth={1.75} />}
            </span>
            <h2
              className={[
                styles.statusHeading,
                owned ? styles.statusOwned : styles.statusAbsent,
              ].join(' ')}
            >
              {owned ? t('card.inCollection') : t('card.notInCollection')}
            </h2>
          </div>
          {owned ? (
            <p className={styles.quantityLine}>
              {t('card.quantity')}:{' '}
              <strong className="tabular">{t('card.pieces', { count: card.quantityOwned })}</strong>
            </p>
          ) : null}
        </>
      ) : null}

      <div className={styles.priceBlock}>
        <span className={styles.priceLabel}>
          {t(guest ? 'guest.estimatedValue' : 'card.currentPrice')}
        </span>
        {guest ? (
          <p className={styles.muted}>
            <strong>{t('guest.lockedShort')}</strong>
            <br />
            {t('guest.lockedText')}
          </p>
        ) : card.marketPriceUah !== null ? (
          <>
            <p className={styles.priceValue}>{formatUah(card.marketPriceUah, locale)}</p>
            <span className={styles.priceApprox}>{priceApproxText}</span>
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
        {guest ? (
          <GuestAddButton itemId={card.id} block>
            + {t('catalog.addToCollection')}
          </GuestAddButton>
        ) : (
          <Link to={addUrl} state={addState}>
            <Button block>
              {owned ? t('catalog.addAnotherCopy') : `+ ${t('catalog.addToCollection')}`}
            </Button>
          </Link>
        )}
      </div>

      {!guest && card.sourceUrl ? (
        <a className={styles.sourceLink} href={card.sourceUrl} target="_blank" rel="noreferrer">
          {openLabel} ↗
        </a>
      ) : null}
    </Card>
  );
}

/**
 * The strip above "Мої екземпляри": the visitor's own purchase and valuation
 * numbers, aggregated across every instance of this coin they own.
 *
 * The two ≈ figures are NOT the same kind of number: "purchased total" is
 * card.purchaseTotalUsd/Eur, the backend's own conversion by the NBU rate on
 * each instance's purchase date — what was actually spent, back then, in
 * whichever secondary currency the viewer picked. "Current value" has no
 * purchase date of its own, so it converts by today's live rate instead
 * (secondaryRate, bootstrap's exchangeRates). The change line is the
 * difference of those two already-converted figures, not a third conversion
 * of its own.
 */
function ValueSummary({
  card,
  locale,
  t,
  secondaryCurrency,
  secondaryRate,
}: {
  card: CatalogCard;
  locale: string;
  t: TFunction;
  secondaryCurrency: SecondaryCurrency;
  secondaryRate: number | null;
}) {
  const currentValue =
    card.marketPriceUah !== null ? Number(card.marketPriceUah) * card.quantityOwned : null;
  const purchaseTotal = Number(card.purchaseTotalUah);
  const change = currentValue !== null ? currentValue - purchaseTotal : null;
  const changePercent =
    change !== null && purchaseTotal > 0 ? (change / purchaseTotal) * 100 : null;
  const symbol = currencySymbol(secondaryCurrency);
  const approxText = (value: string | null) =>
    value !== null ? t('card.approxSecondary', { value, symbol }) : t('dashboard.rateMissing');

  const purchaseTotalSecondary = pickSecondary(
    card.purchaseTotalUsd,
    card.purchaseTotalEur,
    secondaryCurrency,
  );
  const purchaseTotalApprox =
    purchaseTotalSecondary !== null ? Number(purchaseTotalSecondary) : null;
  const currentValueApprox =
    currentValue !== null ? toSecondary(currentValue, secondaryRate) : null;
  const changeApprox =
    currentValueApprox !== null && purchaseTotalApprox !== null
      ? currentValueApprox - purchaseTotalApprox
      : null;

  return (
    <Card className={styles.valueStrip}>
      <div className={styles.valueBox}>
        <span className={styles.valueBoxLabel}>
          {t('card.purchasedTotal')} ({t('card.pieces', { count: card.quantityOwned })})
        </span>
        <p className={`${styles.valueBoxValue} tabular`}>{formatUah(purchaseTotal, locale)}</p>
        <span className={styles.valueBoxUsd}>
          {approxText(formatSecondary(purchaseTotalApprox, locale))}
        </span>
      </div>

      <div className={styles.valueBox}>
        <span className={styles.valueBoxLabel}>{t('card.currentValue')}</span>
        {currentValue !== null ? (
          <>
            <p className={`${styles.valueBoxValue} tabular`}>{formatUah(currentValue, locale)}</p>
            <span className={styles.valueBoxUsd}>
              {approxText(formatSecondary(currentValueApprox, locale))}
            </span>
          </>
        ) : (
          <p className={styles.muted}>{t('catalog.noPrice')}</p>
        )}
      </div>

      <div className={styles.valueBox}>
        <span className={styles.valueBoxLabel}>{t('card.valueChange')}</span>
        {change !== null ? (
          <>
            <p
              className={[
                styles.valueBoxValue,
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
            </p>
            <span className={styles.valueBoxUsd}>
              {approxText(
                changeApprox !== null ? formatSecondarySigned(changeApprox, locale) : null,
              )}
            </span>
          </>
        ) : (
          <p className={styles.muted}>{t('catalog.noPrice')}</p>
        )}
      </div>
    </Card>
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
