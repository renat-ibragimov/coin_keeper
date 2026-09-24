import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';

import { fetchCard, fetchCurrencies } from '@/features/catalog/api';
import { fetchBootstrap } from '@/features/dashboard/api';
import { ApiError } from '@/shared/api/client';
import type { CollectionItemPhotos } from '@/shared/api/types';
import { Button, Card, ErrorState, PageHeader, Skeleton, useToast } from '@/shared/ui';

import {
  deleteCoinPhoto,
  fetchCollectionItem,
  fetchStorageLocations,
  updateCollectionItem,
  uploadCoinPhoto,
} from './api';
import { CoinPhotoCropDialog } from './CoinPhotoCropDialog';
import { COLLECTION_DEPENDENT_KEYS } from './model';
import { PurchaseForm } from './PurchaseForm';
import type { PurchaseValues } from './PurchaseForm';
import styles from './PurchaseFormPage.module.css';
import type { CoinSide } from './SelectedCoin';
import { SelectedCoin } from './SelectedCoin';
import { useCoinPhotoPicker } from './useCoinPhotoPicker';

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

  // What PUT/DELETE last answered, so both sides repaint without a refetch
  // of the whole coin (docs/media.md) — every response already
  // carries the fresh truth for both, so one slot supersedes the instance
  // query's own image fields entirely once anything has been uploaded or
  // removed. `ownership` tracks which side is the owner's own photo, since
  // the crop dialog's answer does not say that on its own.
  const [photos, setPhotos] = useState<CollectionItemPhotos | null>(null);
  const [ownership, setOwnership] = useState<Partial<Record<CoinSide, boolean>>>({});
  const [savingSide, setSavingSide] = useState<CoinSide | null>(null);

  const uploadMutation = useMutation({
    mutationFn: ({ side, blob }: { side: CoinSide; blob: Blob }) =>
      uploadCoinPhoto(editId, side, blob),
    onMutate: ({ side }) => setSavingSide(side),
    onSuccess: (result, { side }) => {
      setPhotos(result);
      setOwnership((current) => ({ ...current, [side]: true }));
      toast.show(t('collectionPhoto.saved'));
    },
    onError: (error) => {
      const rejected = error instanceof ApiError && error.problemType === 'invalid-image';
      toast.show(rejected ? t('collectionPhoto.invalid') : t('errors.generic'));
    },
    onSettled: () => setSavingSide(null),
  });

  const deleteMutation = useMutation({
    mutationFn: (side: CoinSide) => deleteCoinPhoto(editId, side),
    onMutate: (side: CoinSide) => setSavingSide(side),
    onSuccess: (result, side) => {
      setPhotos(result);
      setOwnership((current) => ({ ...current, [side]: false }));
      toast.show(t('collectionPhoto.removed'));
    },
    onError: () => toast.show(t('errors.generic')),
    onSettled: () => setSavingSide(null),
  });

  const photoPicker = useCoinPhotoPicker((side, blob) => uploadMutation.mutate({ side, blob }));

  function isOwnPhoto(side: CoinSide): boolean {
    if (side in ownership) return Boolean(ownership[side]);
    return Boolean(
      side === 'obverse'
        ? instanceQuery.data?.obversePhotoIsOwn
        : instanceQuery.data?.reversePhotoIsOwn,
    );
  }

  const photoOverrides: Partial<Record<CoinSide, string | null>> = {
    obverse: photos
      ? (photos.obverse?.medium ?? null)
      : (instanceQuery.data?.obverseImage?.medium ?? undefined),
    reverse: photos
      ? (photos.reverse?.medium ?? null)
      : (instanceQuery.data?.reverseImage?.medium ?? undefined),
  };

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
          <SelectedCoin
            card={cardQuery.data}
            photos={photoOverrides}
            ownPhoto={{ obverse: isOwnPhoto('obverse'), reverse: isOwnPhoto('reverse') }}
            onPickPhoto={photoPicker.pick}
            onRemovePhoto={(side) => deleteMutation.mutate(side)}
          />
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

      <input
        ref={photoPicker.fileInput}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        className={styles.fileInput}
        onChange={photoPicker.onFileChange}
      />
      <CoinPhotoCropDialog
        key={photoPicker.raw ?? 'none'}
        image={photoPicker.raw}
        busy={savingSide !== null}
        onCancel={photoPicker.cancel}
        onSave={photoPicker.onCropSave}
      />
    </div>
  );
}
