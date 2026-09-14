import { useQuery } from '@tanstack/react-query';
import { ChevronDown } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  fetchAllMaterials,
  fetchDenominations,
  fetchEdgeTypes,
  fetchQualityTypes,
  fetchSeries,
} from '@/features/catalog/api';
import { Combobox, FormRow, Input, Select, Textarea } from '@/shared/ui';

import { COLLECTION_GROUPS, METAL_KINDS } from './coinFields';
import type { CoinFieldErrors, CoinFields } from './coinFields';
import styles from './NewCoinFields.module.css';

interface NewCoinFieldsProps {
  countryId: number | null;
  values: CoinFields;
  errors: CoinFieldErrors;
  onChange: (key: keyof CoinFields, value: string) => void;
}

/**
 * "Про монету" — the catalog record behind a coin the search did not find.
 *
 * Three fields are required beside the country and the name: the year
 * (`issue_year` is NOT NULL and series completeness counts on it), the type
 * and the material (owner, 2026-09-14). Everything else is optional, and all
 * of it below the first four rows hides behind "Більше деталей": the common
 * case is a collector who knows what they bought and not much else.
 */
export function NewCoinFields({ countryId, values, errors, onChange }: NewCoinFieldsProps) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);

  const denominationsQuery = useQuery({
    queryKey: ['denominations', countryId],
    queryFn: () => fetchDenominations(countryId ?? undefined),
    enabled: countryId !== null,
  });
  const seriesQuery = useQuery({
    queryKey: ['series', countryId],
    queryFn: () => fetchSeries(countryId ?? undefined),
    enabled: countryId !== null,
  });
  const materialsQuery = useQuery({
    queryKey: ['materials', 'all'],
    queryFn: fetchAllMaterials,
    staleTime: Infinity,
  });
  const edgeTypesQuery = useQuery({
    queryKey: ['edge-types'],
    queryFn: fetchEdgeTypes,
    staleTime: Infinity,
    enabled: expanded,
  });
  const qualityTypesQuery = useQuery({
    queryKey: ['quality-types'],
    queryFn: fetchQualityTypes,
    staleTime: Infinity,
    enabled: expanded,
  });

  const denominations = denominationsQuery.data ?? [];
  const series = seriesQuery.data ?? [];

  const set = (key: keyof CoinFields) => (value: string) => onChange(key, value);

  return (
    <section className={styles.block} aria-label={t('add.aboutCoin')}>
      <h3 className={styles.title}>{t('add.aboutCoin')}</h3>
      <p className={styles.lead}>{t('add.aboutCoinLead')}</p>

      <FormRow>
        <Input
          label={t('add.year')}
          type="number"
          inputMode="numeric"
          required
          min={1}
          max={2200}
          placeholder="2021"
          value={values.issueYear}
          onChange={(event) => set('issueYear')(event.target.value)}
          error={errors.issueYear}
        />
        {/* The denominations dictionary is seeded from what the catalogue
            holds, so for most issuers there is nothing to pick and the field
            has nothing to say (docs/03-api-contract.md). */}
        {denominations.length > 0 ? (
          <Select
            label={t('add.denomination')}
            value={values.denominationId}
            onChange={(event) => set('denominationId')(event.target.value)}
          >
            <option value="">{t('add.notSpecified')}</option>
            {denominations.map((denomination) => (
              <option key={denomination.id} value={String(denomination.id)}>
                {denomination.label}
              </option>
            ))}
          </Select>
        ) : (
          <Input label={t('add.denomination')} value="" disabled hint={t('add.noDenominations')} />
        )}
      </FormRow>

      <FormRow>
        {/* Series belong to the shared catalog and only an admin creates them
            (docs/04-business-rules.md, rule 2): a personal item may point at
            one, never add one. */}
        <Select
          label={t('add.series')}
          searchable={series.length > 8}
          searchPlaceholder={t('add.seriesSearch')}
          value={values.seriesId}
          disabled={series.length === 0}
          hint={series.length === 0 ? t('add.noSeries') : undefined}
          onChange={(event) => set('seriesId')(event.target.value)}
        >
          <option value="">{t('add.notSpecified')}</option>
          {series.map((item) => (
            <option key={item.id} value={String(item.id)}>
              {item.name}
            </option>
          ))}
        </Select>
        <Select
          label={t('add.collectionGroup')}
          value={values.collectionGroup}
          onChange={(event) => set('collectionGroup')(event.target.value)}
        >
          {COLLECTION_GROUPS.map((group) => (
            <option key={group} value={group}>
              {t(`add.collectionGroups.${group}`)}
            </option>
          ))}
        </Select>
      </FormRow>

      <FormRow>
        {/* Dictionary plus free text in one field: the list is what the
            catalogue already knows, anything else can be typed. */}
        <Combobox
          label={t('add.material')}
          required
          placeholder={t('add.materialPlaceholder')}
          hint={t('add.materialHint')}
          error={errors.material}
          maxLength={200}
          value={values.material}
          onChange={(event) => set('material')(event.target.value)}
          options={(materialsQuery.data ?? []).map((material) => material.name)}
        />
        <Select
          label={t('add.metalKind')}
          value={values.metalKind}
          onChange={(event) => set('metalKind')(event.target.value)}
        >
          {METAL_KINDS.map((kind) => (
            <option key={kind} value={kind}>
              {t(`add.metalKinds.${kind}`)}
            </option>
          ))}
        </Select>
      </FormRow>

      <button
        type="button"
        className={styles.toggle}
        onClick={() => setExpanded((current) => !current)}
        aria-expanded={expanded}
        aria-controls="add-coin-details"
      >
        <ChevronDown
          strokeWidth={2}
          className={[styles.chevron, expanded ? styles.chevronOpen : ''].filter(Boolean).join(' ')}
          aria-hidden="true"
        />
        {t('add.moreDetails')}
      </button>

      <div id="add-coin-details" className={styles.details} hidden={!expanded}>
        <FormRow>
          <Input
            label={t('add.mintage')}
            type="number"
            inputMode="numeric"
            min={0}
            value={values.mintageAnnounced}
            onChange={(event) => set('mintageAnnounced')(event.target.value)}
            error={errors.mintageAnnounced}
          />
          <Input
            label={t('add.weight')}
            inputMode="decimal"
            value={values.weightGrams}
            onChange={(event) => set('weightGrams')(event.target.value)}
            error={errors.weightGrams}
          />
        </FormRow>
        <FormRow>
          <Input
            label={t('add.diameter')}
            inputMode="decimal"
            value={values.diameterMm}
            onChange={(event) => set('diameterMm')(event.target.value)}
            error={errors.diameterMm}
          />
          <Input
            label={t('add.thickness')}
            inputMode="decimal"
            value={values.thicknessMm}
            onChange={(event) => set('thicknessMm')(event.target.value)}
            error={errors.thicknessMm}
          />
        </FormRow>
        <FormRow>
          {/* Both are dictionaries the catalogue parser writes into, so the
              form picks from them rather than offering a text field whose
              value would never match anything (docs/04, §14). */}
          <Select
            label={t('add.edge')}
            value={values.edgeTypeId}
            onChange={(event) => set('edgeTypeId')(event.target.value)}
          >
            <option value="">{t('add.notSpecified')}</option>
            {(edgeTypesQuery.data ?? []).map((edge) => (
              <option key={edge.id} value={String(edge.id)}>
                {edge.name}
              </option>
            ))}
          </Select>
          <Select
            label={t('add.quality')}
            value={values.qualityTypeId}
            onChange={(event) => set('qualityTypeId')(event.target.value)}
          >
            <option value="">{t('add.notSpecified')}</option>
            {(qualityTypesQuery.data ?? []).map((quality) => (
              <option key={quality.id} value={String(quality.id)}>
                {quality.name}
              </option>
            ))}
          </Select>
        </FormRow>
        <FormRow>
          <Input
            label={t('add.shape')}
            maxLength={100}
            value={values.shape}
            onChange={(event) => set('shape')(event.target.value)}
          />
          <Input
            label={t('add.catalogKm')}
            maxLength={100}
            value={values.catalogKm}
            onChange={(event) => set('catalogKm')(event.target.value)}
          />
        </FormRow>
        <FormRow>
          <Input
            label={t('add.catalogUc')}
            maxLength={100}
            value={values.catalogUc}
            onChange={(event) => set('catalogUc')(event.target.value)}
          />
          <Input
            label={t('add.catalogNumista')}
            maxLength={100}
            value={values.catalogNumista}
            onChange={(event) => set('catalogNumista')(event.target.value)}
          />
        </FormRow>
        <Textarea
          label={t('add.coinNotes')}
          hint={t('add.coinNotesHint')}
          maxLength={4000}
          value={values.notes}
          onChange={(event) => set('notes')(event.target.value)}
        />
      </div>
    </section>
  );
}
