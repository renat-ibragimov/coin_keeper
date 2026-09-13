import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom';

import { fetchCard, fetchCurrencies } from '@/features/catalog/api';
import { fetchBootstrap } from '@/features/dashboard/api';
import { ApiError } from '@/shared/api/client';
import type { CatalogListItem } from '@/shared/api/types';
import { coinMaterial } from '@/shared/lib/coinMaterial';
import { coinTitle } from '@/shared/lib/coinTitle';
import { imageSources } from '@/shared/lib/coinImage';
import {
  Badge,
  Button,
  Card,
  CoinImage,
  ErrorState,
  PageHeader,
  Skeleton,
  useToast,
} from '@/shared/ui';

import { createCollectionItem, fetchCollectionItem, updateCollectionItem } from './api';
import { CatalogItemPicker } from './CatalogItemPicker';
import { COLLECTION_DEPENDENT_KEYS } from './model';
import { PurchaseForm } from './PurchaseForm';
import type { PurchaseValues } from './PurchaseForm';
import styles from './PurchaseFormPage.module.css';

/**
 * /collection/coins/new?catalogItemId=  — a new purchase of a catalog item
 * /collection/coins/new                 — pick the item first
 * /collection/coins/:id/edit            — change an existing purchase
 */
export function PurchaseFormPage() {
  const { t, i18n } = useTranslation();
  const { id } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const location = useLocation();
  const toast = useToast();
  const queryClient = useQueryClient();

  const editId = id ? Number.parseInt(id, 10) : null;
  const editing = editId !== null && Number.isFinite(editId);
  const [picked, setPicked] = useState<CatalogListItem | null>(null);

  const instanceQuery = useQuery({
    queryKey: ['collection', 'item', editId],
    queryFn: () => fetchCollectionItem(editId!),
    enabled: editing,
  });
  const queryItemId = Number.parseInt(searchParams.get('catalogItemId') ?? '', 10);
  const catalogItemId = editing
    ? (instanceQuery.data?.catalogItemId ?? null)
    : Number.isFinite(queryItemId) && queryItemId > 0
      ? queryItemId
      : (picked?.id ?? null);

  const cardQuery = useQuery({
    queryKey: ['catalog', 'card', catalogItemId],
    queryFn: () => fetchCard(catalogItemId!),
    enabled: catalogItemId !== null,
  });
  const bootstrapQuery = useQuery({ queryKey: ['bootstrap'], queryFn: fetchBootstrap });
  const currenciesQuery = useQuery({ queryKey: ['currencies'], queryFn: fetchCurrencies });

  const from = (location.state as { from?: string } | null)?.from;
  // The only entry point into editing is a coin's own page, so both the back
  // button and the cancel button return there rather than to the full list.
  const destination =
    from ?? (catalogItemId !== null ? `/catalog/${catalogItemId}` : '/collection/coins');
  const goBack = () => navigate(destination);

  const mutation = useMutation({
    mutationFn: (values: PurchaseValues) =>
      editing
        ? updateCollectionItem(editId!, values)
        : createCollectionItem({ ...values, catalogItemId: catalogItemId! }),
    onSuccess: async () => {
      await Promise.all(
        COLLECTION_DEPENDENT_KEYS.map((key) => queryClient.invalidateQueries({ queryKey: [key] })),
      );
      toast.show(editing ? t('purchase.updated') : t('purchase.created'));
      navigate(destination, { replace: true });
    },
  });

  if (editing && instanceQuery.isError) {
    const notFound = instanceQuery.error instanceof ApiError && instanceQuery.error.status === 404;
    return (
      <ErrorState
        title={notFound ? t('purchase.instanceNotFound') : undefined}
        onRetry={notFound ? undefined : () => void instanceQuery.refetch()}
        actions={
          <Link to="/collection/coins">
            <Button variant="secondary">{t('nav.coins')}</Button>
          </Link>
        }
      />
    );
  }

  const sides = cardQuery.data
    ? ([
        { key: 'obverse' as const, image: cardQuery.data.obverseImage, label: t('card.obverse') },
        { key: 'reverse' as const, image: cardQuery.data.reverseImage, label: t('card.reverse') },
      ] as const)
    : [];

  return (
    <div className={styles.page}>
      <PageHeader
        align="center"
        onBack={catalogItemId !== null ? goBack : undefined}
        title={editing ? t('purchase.editTitle') : t('card.addPurchase')}
        subtitle={editing ? t('purchase.editSubtitle') : t('purchase.subtitle')}
      />

      {catalogItemId === null ? (
        <Card>
          <CatalogItemPicker
            onSelect={(item) => {
              setPicked(item);
              setSearchParams({ catalogItemId: String(item.id) }, { replace: true });
            }}
          />
        </Card>
      ) : (
        <div className={styles.content}>
          {cardQuery.data ? (
            <div className={styles.coinHeader}>
              <div className={styles.coinBadges}>
                {cardQuery.data.isOwn ? <Badge tone="accent">{t('catalog.badgeOwn')}</Badge> : null}
                {cardQuery.data.isArchived ? (
                  <Badge tone="warning">{t('catalog.badgeArchived')}</Badge>
                ) : null}
              </div>
              <Link to={`/catalog/${cardQuery.data.id}`} className={styles.coinTitle}>
                {coinTitle(cardQuery.data, i18n.language)}
              </Link>
              <div className={styles.coinMeta}>
                {[
                  cardQuery.data.country,
                  cardQuery.data.seriesName,
                  String(cardQuery.data.year),
                  cardQuery.data.denomination?.label,
                  coinMaterial(cardQuery.data),
                ]
                  .filter(Boolean)
                  .join(' · ')}
              </div>
              {!editing ? (
                <button
                  type="button"
                  className={styles.changeItem}
                  onClick={() => {
                    setPicked(null);
                    setSearchParams({}, { replace: true });
                  }}
                >
                  {t('purchase.changeItem')}
                </button>
              ) : null}
            </div>
          ) : cardQuery.isError ? (
            <ErrorState
              title={t('card.notFoundTitle')}
              actions={
                <Link to="/catalog">
                  <Button variant="secondary">{t('common.backToCatalog')}</Button>
                </Link>
              }
            />
          ) : (
            <Skeleton width={280} height={32} style={{ margin: '0 auto' }} />
          )}

          {cardQuery.data ? (
            <div className={styles.photos}>
              {sides.map((side) => (
                <figure key={side.key} className={styles.photo}>
                  <CoinImage
                    {...imageSources(side.image, 'card')}
                    alt=""
                    className={styles.photoImage}
                  />
                  <figcaption className={styles.photoLabel}>{side.label}</figcaption>
                </figure>
              ))}
            </div>
          ) : null}

          <Card className={styles.form}>
            {cardQuery.data && bootstrapQuery.data && (!editing || instanceQuery.data) ? (
              <PurchaseForm
                key={editing ? `edit-${editId}` : `new-${catalogItemId}`}
                initial={editing ? instanceQuery.data : undefined}
                defaultGrade={bootstrapQuery.data.settings.defaultGrade}
                currencies={currenciesQuery.data ?? []}
                busy={mutation.isPending}
                submitError={mutation.error}
                onSubmit={(values) => mutation.mutate(values)}
                onCancel={goBack}
              />
            ) : cardQuery.isError ? null : (
              <div className={styles.formSkeleton}>
                <Skeleton height={42} />
                <Skeleton height={42} />
                <Skeleton height={42} />
                <Skeleton height={96} />
              </div>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
