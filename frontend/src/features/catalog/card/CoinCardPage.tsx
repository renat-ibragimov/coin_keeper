import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';

import { ApiError } from '@/shared/api/client';
import type { CatalogCard } from '@/shared/api/types';
import { coinTitle } from '@/shared/lib/coinTitle';
import { formatDate, formatUah } from '@/shared/lib/format';
import { priceSourceLabel } from '@/shared/lib/priceSource';
import {
  Badge,
  Breadcrumbs,
  Button,
  Card,
  CoinImage,
  ErrorState,
  Lightbox,
  PropertyList,
  Skeleton,
} from '@/shared/ui';

import { fetchCard, fetchOwnInstances, fetchPrices } from '../api';
import { InstancesList } from './InstancesList';
import { PriceHistoryChart } from './PriceHistoryChart';
import { specRows } from './specs';
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
  const locale = i18n.language;
  const navigate = useNavigate();
  const location = useLocation();
  const [enlarged, setEnlarged] = useState<'obverse' | 'reverse' | null>(null);

  const pricesQuery = useQuery({
    queryKey: ['catalog', 'prices', card.id],
    queryFn: () => fetchPrices(card.id),
  });
  const instancesQuery = useQuery({
    queryKey: ['catalog', 'instances', card.id],
    queryFn: () => fetchOwnInstances(card.id),
  });

  const title = coinTitle(card);
  const subtitle = [card.denomination, card.country, String(card.year)].filter(Boolean).join(' · ');
  const owned = card.quantityOwned > 0;
  const valuation =
    owned && card.marketPriceUah !== null
      ? formatUah(Number(card.marketPriceUah) * card.quantityOwned, locale)
      : null;
  const sides = [
    { key: 'obverse' as const, url: card.obverseImageUrl, label: t('card.obverse') },
    { key: 'reverse' as const, url: card.reverseImageUrl, label: t('card.reverse') },
  ];
  const enlargedSide = sides.find((side) => side.key === enlarged);

  // The catalog keeps its filters in the URL, so going back through history
  // restores the exact listing; a direct link has nowhere to go but the catalog.
  const goBack = () => {
    if (location.key !== 'default') navigate(-1);
    else navigate('/catalog');
  };

  const latestPrice = pricesQuery.data?.find((point) => !point.isSuspect);

  return (
    <div className={styles.page}>
      <div className={styles.topBar}>
        <Breadcrumbs
          items={[{ label: t('nav.catalog'), to: '/catalog' }, { label: t('card.crumb') }]}
        />
        <Button variant="ghost" size="sm" onClick={goBack}>
          ← {t('common.back')}
        </Button>
      </div>

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
        <div className={styles.badges}>
          {card.isOwn ? <Badge tone="accent">{t('catalog.badgeOwn')}</Badge> : null}
          {card.isArchived ? <Badge tone="warning">{t('catalog.badgeArchived')}</Badge> : null}
        </div>
        <h1 className={styles.title}>{title}</h1>
        <p className={styles.subtitle}>{subtitle}</p>
        <p className={styles.lead}>{t('card.lead')}</p>
      </header>

      <div className={styles.layout}>
        <section className={styles.photos} aria-label={t('card.photosLabel')}>
          {sides.map((side) => (
            <figure key={side.key} className={styles.photo}>
              <CoinImage src={side.url} alt="" fit="contain" className={styles.photoFrame} />
              <figcaption className={styles.photoLabel}>{side.label}</figcaption>
              {side.url ? (
                <button
                  type="button"
                  className={styles.zoom}
                  onClick={() => setEnlarged(side.key)}
                  aria-label={`${t('card.enlarge')} — ${side.label}`}
                >
                  ⌕ {t('card.enlarge')}
                </button>
              ) : null}
            </figure>
          ))}
        </section>

        <aside className={styles.side}>
          <Card>
            <div className={styles.sideHeader}>
              <h2 className={styles.sideTitle}>{t('card.inCollection')}</h2>
              <span className={owned ? styles.ownedMark : styles.missingMark} aria-hidden="true">
                {owned ? '✓' : '○'}
              </span>
            </div>
            <PropertyList
              rows={[
                {
                  key: 'status',
                  label: t('card.status'),
                  value: owned ? (
                    <Badge tone="success">✓ {t('catalog.badgeInCollection')}</Badge>
                  ) : (
                    <Badge tone="danger">✕ {t('catalog.badgeMissing')}</Badge>
                  ),
                },
                {
                  key: 'quantity',
                  label: t('card.quantity'),
                  value: (
                    <span className="tabular">
                      {t('card.pieces', { count: card.quantityOwned })}
                    </span>
                  ),
                },
              ]}
            />
          </Card>

          {owned ? (
            <Card>
              <dl className={styles.money}>
                <div className={styles.moneyRow}>
                  <dt>{t('card.purchasedFor')}</dt>
                  <dd className="tabular">{formatUah(card.purchaseTotalUah, locale) ?? '—'}</dd>
                </div>
                <div className={styles.moneyRow}>
                  <dt>{t('card.valuation')}</dt>
                  <dd className="tabular">
                    {valuation ?? <span className={styles.muted}>{t('catalog.noPrice')}</span>}
                  </dd>
                </div>
              </dl>
            </Card>
          ) : null}

          <Card>
            <h2 className={styles.sideTitle}>{t('card.actions')}</h2>
            <div className={styles.actions}>
              <Link to={`/collection/new?catalogItemId=${card.id}`} className={styles.actionLink}>
                <Button block>+ {t('card.addPurchase')}</Button>
              </Link>
              <Button block variant="secondary" disabled title={t('card.ownPriceSoon')}>
                ⌂ {t('card.ownPrice')}
              </Button>
              <span className={styles.actionNote}>{t('card.ownPriceSoon')}</span>
            </div>
          </Card>

          <div className={styles.infoBox}>
            <span aria-hidden="true">ⓘ</span>
            <span>{t('card.priceVisibility')}</span>
          </div>
        </aside>

        <Card className={styles.specs}>
          <h2 className={styles.sectionTitle}>{t('card.specs')}</h2>
          <PropertyList rows={specRows(card, t, locale)} columns={2} />
          {card.notes ? <p className={styles.notes}>{card.notes}</p> : null}
          {card.sourceUrl ? (
            <a className={styles.sourceLink} href={card.sourceUrl} target="_blank" rel="noreferrer">
              {t('catalog.sourceLink')} ↗
            </a>
          ) : null}
        </Card>

        <Card className={styles.prices}>
          <div className={styles.sectionHeader}>
            <h2 className={styles.sectionTitle}>{t('card.priceHistory')}</h2>
            {latestPrice ? (
              <span className={styles.priceCaption}>
                {t('card.priceSource', { source: priceSourceLabel(latestPrice.source, t) })} ·{' '}
                {t('card.priceUpdated', { date: formatDate(latestPrice.observedAt, locale) })}
              </span>
            ) : null}
          </div>
          {pricesQuery.isPending ? <Skeleton height={180} /> : null}
          {pricesQuery.isError ? <ErrorState onRetry={() => void pricesQuery.refetch()} /> : null}
          {pricesQuery.data ? <PriceHistoryChart items={pricesQuery.data} /> : null}
        </Card>

        <Card className={styles.instances}>
          <h2 className={styles.sectionTitle}>{t('card.instances')}</h2>
          {instancesQuery.isError ? (
            <ErrorState onRetry={() => void instancesQuery.refetch()} />
          ) : (
            <InstancesList items={instancesQuery.data} loading={instancesQuery.isPending} />
          )}
        </Card>
      </div>

      <Lightbox
        open={enlargedSide !== undefined}
        onClose={() => setEnlarged(null)}
        label={`${enlargedSide?.label ?? ''} — ${title}`}
      >
        <CoinImage
          src={enlargedSide?.url}
          alt={`${enlargedSide?.label ?? ''} — ${title}`}
          fit="contain"
          className={styles.lightboxImage}
        />
      </Lightbox>
    </div>
  );
}

function CardSkeleton() {
  return (
    <div className={styles.page} aria-busy="true">
      <Skeleton width={200} height={16} />
      <div>
        <Skeleton width={320} height={44} />
        <Skeleton width={220} height={20} style={{ marginTop: 8 }} />
      </div>
      <div className={styles.layout}>
        <div className={styles.photos}>
          <Skeleton height={300} />
          <Skeleton height={300} />
        </div>
        <div className={styles.side}>
          <Skeleton height={120} />
          <Skeleton height={100} />
          <Skeleton height={160} />
        </div>
        <Skeleton height={260} style={{ gridArea: 'specs' }} />
        <Skeleton height={220} style={{ gridArea: 'prices' }} />
        <Skeleton height={160} style={{ gridArea: 'instances' }} />
      </div>
    </div>
  );
}
