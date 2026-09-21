import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  fetchAllMaterials, fetchCountries, fetchDenominations, fetchSeries,
} from '@/features/catalog/api';
import { NewCoinFields } from '@/features/collection/add/NewCoinFields';
import type { CoinFields } from '@/features/collection/add/coinFields';
import { CoinPhotoCropDialog } from '@/features/collection/CoinPhotoCropDialog';
import type { CoinSide } from '@/features/collection/SelectedCoin';
import { useCoinPhotoPicker } from '@/features/collection/useCoinPhotoPicker';
import type { CatalogCard, CatalogItemUpdate } from '@/shared/api/types';
import { imageSources } from '@/shared/lib/coinImage';
import { Button, Input, Modal, Select } from '@/shared/ui';

import styles from './ProposalEditor.module.css';

type PhotoEdit = { kind: 'replace'; blob: Blob; url: string } | { kind: 'remove' };

function text(value: unknown): string { return value == null ? '' : String(value); }

function initialFields(card: CatalogCard): CoinFields {
  return {
    issueYear: String(card.year),
    denomination: card.denomination?.label ?? card.denominationText ?? '',
    series: card.seriesName ?? '', collectionGroup: card.collectionGroup,
    material: card.composition?.name ?? card.material ?? '', metalKind: card.metalKind,
    mintageAnnounced: text(card.mintageAnnounced), weightGrams: text(card.weightGrams),
    diameterMm: text(card.diameterMm), thicknessMm: text(card.thicknessMm),
    edgeTypeId: text(card.edgeType?.id), qualityTypeId: text(card.qualityType?.id),
    shape: card.shape ?? '', catalogNumber: card.catalogNumber ?? '',
    description: card.description?.general ?? '',
    descriptionObverse: card.description?.obverse ?? '',
    descriptionReverse: card.description?.reverse ?? '',
  };
}

function nullable(value: string) { return value.trim() || null; }
function numberOrNull(value: string) { return value.trim() ? Number(value) : null; }

export function ProposalEditor({
  card, open, busy, onCancel, onApprove,
}: {
  card: CatalogCard; open: boolean; busy: boolean; onCancel: () => void;
  onApprove: (body: CatalogItemUpdate, photos: Partial<Record<CoinSide, PhotoEdit>>) => void;
}) {
  const { t } = useTranslation();
  const [countryId, setCountryId] = useState(card.countryId);
  const [title, setTitle] = useState(card.titleOriginal);
  const [values, setValues] = useState(() => initialFields(card));
  const [photos, setPhotos] = useState<Partial<Record<CoinSide, PhotoEdit>>>({});
  const countries = useQuery({ queryKey: ['countries', 'all'], queryFn: () => fetchCountries('all') });
  const denominations = useQuery({ queryKey: ['denominations', countryId], queryFn: () => fetchDenominations(countryId) });
  const series = useQuery({ queryKey: ['series', countryId], queryFn: () => fetchSeries(countryId) });
  const materials = useQuery({ queryKey: ['materials', 'all'], queryFn: fetchAllMaterials });

  const picker = useCoinPhotoPicker((side, blob) => {
    setPhotos((current) => {
      const old = current[side];
      if (old?.kind === 'replace') URL.revokeObjectURL(old.url);
      return { ...current, [side]: { kind: 'replace', blob, url: URL.createObjectURL(blob) } };
    });
  });
  const preview = (side: CoinSide) => {
    const edit = photos[side];
    if (edit?.kind === 'replace') return edit.url;
    if (edit?.kind === 'remove') return null;
    return imageSources(side === 'obverse' ? card.obverseImage : card.reverseImage, 'card').src;
  };
  const remove = (side: CoinSide) => setPhotos((current) => ({ ...current, [side]: { kind: 'remove' } }));
  const match = <T extends { id: number }>(rows: T[] | undefined, value: string, label: (row: T) => string) => {
    const found = rows?.find((row) => label(row).toLocaleLowerCase() === value.trim().toLocaleLowerCase());
    return { id: found?.id ?? null, own: found ? null : nullable(value) };
  };
  const submit = () => {
    const denomination = match(denominations.data, values.denomination, (row) => row.label);
    const seriesValue = match(series.data, values.series, (row) => row.name);
    const material = match(materials.data, values.material, (row) => row.name);
    onApprove({
      countryId, titleOriginal: title.trim(), issueYear: Number(values.issueYear),
      collectionGroup: values.collectionGroup, metalKind: values.metalKind,
      denominationId: denomination.id, denominationText: denomination.own,
      seriesId: seriesValue.id, seriesText: seriesValue.own,
      compositionId: material.id, material: material.own,
      mintageAnnounced: numberOrNull(values.mintageAnnounced),
      weightGrams: nullable(values.weightGrams), diameterMm: nullable(values.diameterMm),
      thicknessMm: nullable(values.thicknessMm), edgeTypeId: numberOrNull(values.edgeTypeId),
      qualityTypeId: numberOrNull(values.qualityTypeId), shape: nullable(values.shape),
      catalogNumber: nullable(values.catalogNumber), description: nullable(values.description),
      descriptionObverse: nullable(values.descriptionObverse),
      descriptionReverse: nullable(values.descriptionReverse),
    }, photos);
  };

  return <>
    <input ref={picker.fileInput} type="file" accept="image/jpeg,image/png,image/webp" hidden onChange={picker.onFileChange} />
    <Modal open={open} onClose={onCancel} title={t('admin.proposals.editTitle')} footer={<>
      <Button variant="secondary" onClick={onCancel} disabled={busy}>{t('common.cancel')}</Button>
      <Button onClick={submit} loading={busy} disabled={!title.trim() || !values.issueYear}>{t('admin.proposals.approveChanges')}</Button>
    </>}>
      <div className={styles.form}>
        <Select label={t('add.country')} value={countryId} onChange={(event) => setCountryId(Number(event.target.value))}>
          {(countries.data ?? []).map((country) => <option key={country.id} value={country.id}>{country.name}</option>)}
        </Select>
        <Input label={t('add.coinTitle')} value={title} onChange={(event) => setTitle(event.target.value)} required />
        <NewCoinFields countryId={countryId} values={values} errors={{}}
          onChange={(key, value) => setValues((current) => ({ ...current, [key]: value }))}
          photos={{ obverse: preview('obverse'), reverse: preview('reverse') }}
          onPickPhoto={picker.pick} onRemovePhoto={remove} />
      </div>
    </Modal>
    <CoinPhotoCropDialog image={picker.raw} busy={false} onCancel={picker.cancel} onSave={picker.onCropSave} />
  </>;
}
