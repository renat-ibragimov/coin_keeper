import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import type { FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import { useAuth } from '@/features/auth/useAuth';
import { ApiError } from '@/shared/api/client';
import type { CatalogItemCreate, CollectionGroup, MetalKind } from '@/shared/api/types';
import { parseDecimal } from '@/shared/lib/format';
import {
  Breadcrumbs,
  Button,
  Card,
  FormActions,
  FormError,
  FormRow,
  FormSection,
  FormStack,
  Input,
  PageHeader,
  Select,
  Textarea,
  Toggle,
  useToast,
} from '@/shared/ui';

import { createCatalogItem, fetchCountries, fetchDenominations, fetchSeries } from '../api';
import styles from './CreateItemPage.module.css';

const GROUPS: CollectionGroup[] = ['circulation', 'commemorative', 'collector', 'other'];
const METALS: MetalKind[] = ['precious', 'base', 'unknown'];
const GROUP_LABELS: Record<CollectionGroup, string> = {
  circulation: 'catalog.typeCirculation',
  commemorative: 'catalog.typeCommemorative',
  collector: 'catalog.typeCollector',
  other: 'catalog.typeOther',
};
const METAL_LABELS: Record<MetalKind, string> = {
  precious: 'catalog.metalPrecious',
  base: 'catalog.metalBase',
  unknown: 'catalog.metalUnknown',
};

interface Fields {
  titleOriginal: string;
  titleUk: string;
  titleEn: string;
  countryId: string;
  seriesId: string;
  issueYear: string;
  denominationId: string;
  collectionGroup: CollectionGroup;
  metalKind: MetalKind;
  material: string;
  catalogKm: string;
  catalogUc: string;
  catalogNumista: string;
  mintageAnnounced: string;
  diameterMm: string;
  weightGrams: string;
  notes: string;
}

type FieldErrors = Partial<Record<keyof Fields, string>>;

const EMPTY: Fields = {
  titleOriginal: '',
  titleUk: '',
  titleEn: '',
  countryId: '',
  seriesId: '',
  issueYear: '',
  denominationId: '',
  collectionGroup: 'commemorative',
  metalKind: 'unknown',
  material: '',
  catalogKm: '',
  catalogUc: '',
  catalogNumista: '',
  mintageAnnounced: '',
  diameterMm: '',
  weightGrams: '',
  notes: '',
};

const blank = (value: string) => (value.trim() ? value.trim() : null);
const intOrNull = (value: string) => {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) ? parsed : null;
};

/** /catalog/new — a personal catalog item; an administrator may make it shared. */
export function CreateItemPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const toast = useToast();
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';

  const [fields, setFields] = useState<Fields>(EMPTY);
  const [shared, setShared] = useState(false);
  const [errors, setErrors] = useState<FieldErrors>({});

  const countryId = intOrNull(fields.countryId) ?? undefined;
  const countriesQuery = useQuery({ queryKey: ['countries'], queryFn: fetchCountries });
  const seriesQuery = useQuery({
    queryKey: ['series', 'list', countryId],
    queryFn: () => fetchSeries(countryId),
    enabled: countryId !== undefined,
  });
  const denominationsQuery = useQuery({
    queryKey: ['denominations', countryId],
    queryFn: () => fetchDenominations(countryId),
    enabled: countryId !== undefined,
  });

  const mutation = useMutation({
    mutationFn: (body: CatalogItemCreate) => createCatalogItem(body),
    onSuccess: async (card) => {
      await queryClient.invalidateQueries({ queryKey: ['catalog'] });
      await queryClient.invalidateQueries({ queryKey: ['bootstrap'] });
      toast.show(t('createItem.created'));
      navigate(`/catalog/${card.id}`, { replace: true });
    },
  });

  const set = (key: keyof Fields) => (value: string) => {
    setFields((current) => {
      const next = { ...current, [key]: value };
      // A new country invalidates the series and denomination chosen under the old one.
      if (key === 'countryId') {
        next.seriesId = '';
        next.denominationId = '';
      }
      return next;
    });
    setErrors((current) => ({ ...current, [key]: undefined }));
  };

  function validate(): FieldErrors {
    const next: FieldErrors = {};
    if (!fields.titleOriginal.trim() && !fields.titleUk.trim())
      next.titleOriginal = 'common.required';
    if (!fields.countryId) next.countryId = 'common.required';
    const year = intOrNull(fields.issueYear);
    if (year === null || year < 1 || year > 2200) next.issueYear = 'createItem.yearInvalid';
    for (const key of ['mintageAnnounced', 'diameterMm', 'weightGrams'] as const) {
      if (fields[key].trim() && parseDecimal(fields[key]) === null)
        next[key] = 'common.invalidNumber';
    }
    return next;
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    const next = validate();
    setErrors(next);
    if (Object.keys(next).length > 0) return;
    const titleOriginal = fields.titleOriginal.trim() || fields.titleUk.trim();
    mutation.mutate({
      countryId: Number(fields.countryId),
      seriesId: intOrNull(fields.seriesId),
      denominationId: intOrNull(fields.denominationId),
      collectionGroup: fields.collectionGroup,
      titleOriginal,
      titleUk: blank(fields.titleUk),
      titleEn: blank(fields.titleEn),
      issueYear: Number(fields.issueYear),
      metalKind: fields.metalKind,
      material: blank(fields.material),
      catalogKm: blank(fields.catalogKm),
      catalogUc: blank(fields.catalogUc),
      catalogNumista: blank(fields.catalogNumista),
      mintageAnnounced: fields.mintageAnnounced.trim()
        ? Math.round(parseDecimal(fields.mintageAnnounced) ?? 0)
        : null,
      diameterMm: fields.diameterMm.trim() ? String(parseDecimal(fields.diameterMm)) : null,
      weightGrams: fields.weightGrams.trim() ? String(parseDecimal(fields.weightGrams)) : null,
      notes: blank(fields.notes),
      shared: isAdmin && shared,
    });
  }

  const message = (key: keyof Fields) => (errors[key] ? t(errors[key]!) : undefined);
  const submitError = mutation.error
    ? mutation.error instanceof ApiError && mutation.error.problemType === 'admin-required'
      ? t('createItem.adminRequired')
      : mutation.error instanceof ApiError && mutation.error.problemType === 'invalid-reference'
        ? t('createItem.invalidReference')
        : t('errors.generic')
    : null;

  return (
    <div className={styles.page}>
      <PageHeader
        above={
          <Breadcrumbs
            items={[{ label: t('nav.catalog'), to: '/catalog' }, { label: t('catalog.createOwn') }]}
          />
        }
        title={t('catalog.createOwn')}
        subtitle={t('createItem.subtitle')}
      />

      <form onSubmit={submit} noValidate className={styles.form}>
        <Card>
          <FormStack>
            <FormError>{submitError}</FormError>
            <FormSection title={t('createItem.sectionBasics')}>
              <FormRow>
                <Input
                  label={t('createItem.title')}
                  required
                  value={fields.titleOriginal}
                  onChange={(event) => set('titleOriginal')(event.target.value)}
                  error={message('titleOriginal')}
                  hint={t('createItem.titleHint')}
                  maxLength={500}
                />
                <Input
                  label={t('createItem.titleUk')}
                  value={fields.titleUk}
                  onChange={(event) => set('titleUk')(event.target.value)}
                  hint={t('createItem.titleUkHint')}
                  maxLength={500}
                />
              </FormRow>
              <FormRow>
                <Select
                  label={t('catalog.country')}
                  required
                  value={fields.countryId}
                  onChange={(event) => set('countryId')(event.target.value)}
                  error={message('countryId')}
                >
                  <option value="">{t('createItem.pickCountry')}</option>
                  {(countriesQuery.data ?? []).map((country) => (
                    <option key={country.id} value={country.id}>
                      {country.name}
                    </option>
                  ))}
                </Select>
                <Select
                  label={t('catalog.tableSeries')}
                  value={fields.seriesId}
                  onChange={(event) => set('seriesId')(event.target.value)}
                  disabled={countryId === undefined}
                >
                  <option value="">{t('createItem.noSeries')}</option>
                  {(seriesQuery.data ?? []).map((series) => (
                    <option key={series.id} value={series.id}>
                      {series.name}
                    </option>
                  ))}
                </Select>
              </FormRow>
              <FormRow>
                <Input
                  label={t('createItem.year')}
                  type="number"
                  inputMode="numeric"
                  required
                  min={1}
                  max={2200}
                  value={fields.issueYear}
                  onChange={(event) => set('issueYear')(event.target.value)}
                  error={message('issueYear')}
                />
                <Select
                  label={t('catalog.denomination')}
                  value={fields.denominationId}
                  onChange={(event) => set('denominationId')(event.target.value)}
                  disabled={countryId === undefined}
                >
                  <option value="">{t('createItem.noDenomination')}</option>
                  {(denominationsQuery.data ?? []).map((denomination) => (
                    <option key={denomination.id} value={denomination.id}>
                      {denomination.label}
                    </option>
                  ))}
                </Select>
              </FormRow>
              <FormRow>
                <Select
                  label={t('catalog.type')}
                  value={fields.collectionGroup}
                  onChange={(event) => set('collectionGroup')(event.target.value)}
                >
                  {GROUPS.map((group) => (
                    <option key={group} value={group}>
                      {t(GROUP_LABELS[group])}
                    </option>
                  ))}
                </Select>
                <Select
                  label={t('catalog.metal')}
                  value={fields.metalKind}
                  onChange={(event) => set('metalKind')(event.target.value)}
                >
                  {METALS.map((metal) => (
                    <option key={metal} value={metal}>
                      {t(METAL_LABELS[metal])}
                    </option>
                  ))}
                </Select>
              </FormRow>
            </FormSection>

            <FormSection title={t('createItem.sectionDetails')}>
              <FormRow>
                <Input
                  label={t('card.specMaterial')}
                  value={fields.material}
                  onChange={(event) => set('material')(event.target.value)}
                  placeholder={t('createItem.materialPlaceholder')}
                  maxLength={200}
                />
                <Input
                  label={t('createItem.titleEn')}
                  value={fields.titleEn}
                  onChange={(event) => set('titleEn')(event.target.value)}
                  maxLength={500}
                />
              </FormRow>
              <div className={styles.threeColumns}>
                <Input
                  label="KM#"
                  value={fields.catalogKm}
                  onChange={(event) => set('catalogKm')(event.target.value)}
                  maxLength={100}
                />
                <Input
                  label="UC#"
                  value={fields.catalogUc}
                  onChange={(event) => set('catalogUc')(event.target.value)}
                  maxLength={100}
                />
                <Input
                  label="Numista"
                  value={fields.catalogNumista}
                  onChange={(event) => set('catalogNumista')(event.target.value)}
                  maxLength={100}
                />
              </div>
              <div className={styles.threeColumns}>
                <Input
                  label={t('card.specMintage')}
                  inputMode="numeric"
                  value={fields.mintageAnnounced}
                  onChange={(event) => set('mintageAnnounced')(event.target.value)}
                  error={message('mintageAnnounced')}
                />
                <Input
                  label={`${t('card.specDiameter')}, ${t('units.mm')}`}
                  inputMode="decimal"
                  value={fields.diameterMm}
                  onChange={(event) => set('diameterMm')(event.target.value)}
                  error={message('diameterMm')}
                />
                <Input
                  label={`${t('card.specWeight')}, ${t('units.g')}`}
                  inputMode="decimal"
                  value={fields.weightGrams}
                  onChange={(event) => set('weightGrams')(event.target.value)}
                  error={message('weightGrams')}
                />
              </div>
              <Textarea
                label={t('createItem.notes')}
                value={fields.notes}
                onChange={(event) => set('notes')(event.target.value)}
                placeholder={t('createItem.notesPlaceholder')}
                maxLength={4000}
              />
            </FormSection>

            {isAdmin ? (
              <div className={styles.adminBox}>
                <Toggle checked={shared} onChange={setShared} label={t('createItem.shared')} />
                <p className={styles.adminHint}>{t('createItem.sharedHint')}</p>
              </div>
            ) : (
              <p className={styles.note}>{t('createItem.personalNote')}</p>
            )}

            <FormActions>
              <Button type="button" variant="secondary" onClick={() => navigate('/catalog')}>
                {t('common.cancel')}
              </Button>
              <Button type="submit" loading={mutation.isPending}>
                {t('createItem.submit')}
              </Button>
            </FormActions>
          </FormStack>
        </Card>
      </form>
    </div>
  );
}
