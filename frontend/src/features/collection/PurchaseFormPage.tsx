import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';

import { fetchCard, fetchCurrencies } from '@/features/catalog/api';
import { fetchBootstrap } from '@/features/dashboard/api';
import { ApiError } from '@/shared/api/client';
import { Button, Card, ErrorState, PageHeader, Skeleton, useToast } from '@/shared/ui';

import { fetchCollectionItem, fetchStorageLocations, updateCollectionItem } from './api';
import { COLLECTION_DEPENDENT_KEYS } from './model';
import { PurchaseForm } from './PurchaseForm';
import type { PurchaseValues } from './PurchaseForm';
import styles from './PurchaseFormPage.module.css';
import { SelectedCoin } from './SelectedCoin';

/**
 * `/collection/coins/:id/edit` — change an existing purchase.
 *
 * Recording a new one lives on `/collection/add` instead, where the coin may
 * also be one the catalog has never heard of; here the coin is settled and
 * only the purchase itself is editable.
 */
export function PurchaseFormPage() {
  const { t } = useTranslation();
  const { id } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const toast = useToast();
  const queryClient = useQueryClient();

  const editId = Number.parseInt(id ?? '', 10);

  const instanceQuery = useQuery({
    queryKey: ['collection', 'item', editId],
    queryFn: () => fetchCollectionItem(editId),
    enabled: Number.isFinite(editId),
  });
  const catalogItemId = instanceQuery.data?.catalogItemId ?? null;

  const cardQuery = useQuery({
    queryKey: ['catalog', 'card', catalogItemId],
    queryFn: () => fetchCard(catalogItemId!),
    enabled: catalogItemId !== null,
  });
  const bootstrapQuery = useQuery({ queryKey: ['bootstrap'], queryFn: fetchBootstrap });
  const currenciesQuery = useQuery({ queryKey: ['currencies'], queryFn: fetchCurrencies });
  const storageLocationsQuery = useQuery({
    queryKey: ['collection', 'storage-locations'],
    queryFn: fetchStorageLocations,
  });

  const from = (location.state as { from?: string } | null)?.from;
  // The only entry point into editing is a coin's own page, so both the back
  // button and the cancel button return there rather than to the full list.
  const destination =
    from ?? (catalogItemId !== null ? `/catalog/${catalogItemId}` : '/collection/coins');
  const goBack = () => navigate(destination);

  const mutation = useMutation({
    mutationFn: (values: PurchaseValues) => updateCollectionItem(editId, values),
    onSuccess: async () => {
      await Promise.all(
        COLLECTION_DEPENDENT_KEYS.map((key) => queryClient.invalidateQueries({ queryKey: [key] })),
      );
      toast.show(t('purchase.updated'));
      navigate(destination, { replace: true });
    },
  });

  if (instanceQuery.isError) {
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

  return (
    <div className={styles.page}>
      <PageHeader
        align="center"
        onBack={goBack}
        title={t('purchase.editTitle')}
        subtitle={t('purchase.editSubtitle')}
      />

      <div className={styles.content}>
        {cardQuery.data ? (
          <SelectedCoin card={cardQuery.data} />
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

        <Card className={styles.form}>
          {cardQuery.data && bootstrapQuery.data && instanceQuery.data ? (
            <PurchaseForm
              key={`edit-${editId}`}
              initial={instanceQuery.data}
              defaultGrade={bootstrapQuery.data.settings.defaultGrade}
              defaultStorageLocation={bootstrapQuery.data.settings.defaultStorageLocation}
              storageLocations={(storageLocationsQuery.data ?? []).map((l) => l.name)}
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
    </div>
  );
}
