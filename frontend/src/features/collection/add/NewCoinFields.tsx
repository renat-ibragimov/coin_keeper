import { useQuery } from '@tanstack/react-query';
import { ChevronDown, Pencil, Plus, X } from 'lucide-react';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  fetchAllMaterials,
  fetchCountries,
  fetchDenominations,
  fetchEdgeTypes,
  fetchQualityTypes,
  fetchSeries,
} from '@/features/catalog/api';
import { buildYearList, computeYearBounds } from '@/shared/lib/yearRange';
import { Combobox, FormRow, Input, Select, Textarea } from '@/shared/ui';

import type { CoinSide } from '../SelectedCoin';
import photoStyles from '../SelectedCoin.module.css';
import { COLLECTION_GROUPS, METAL_KINDS } from './coinFields';
import type { CoinFieldErrors, CoinFields } from './coinFields';
import styles from './NewCoinFields.module.css';

interface NewCoinFieldsProps {
  countryId: number | null;
  values: CoinFields;
  errors: CoinFieldErrors;
  onChange: (key: keyof CoinFields, value: string) => void;
  /** Local preview URLs of the photos picked for the coin that is about to be
   *  created — there is no server side yet to hold them (docs/06-media-storage.md:
   *  the upload happens after the purchase itself is saved). */
  photos?: Partial<Record<CoinSide, string | null>>;
  onPickPhoto?: (side: CoinSide) => void;
  onRemovePhoto?: (side: CoinSide) => void;
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
export function NewCoinFields({
  countryId,
  values,
  errors,
  onChange,
  photos,
  onPickPhoto,
  onRemovePhoto,
}: NewCoinFieldsProps) {
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
  // Already in the cache — the country picker above fetched it.
  const countriesQuery = useQuery({
    queryKey: ['countries', 'all'],
    queryFn: () => fetchCountries('all'),
    staleTime: Infinity,
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
  const yearOptions = useMemo(() => {
    const country = (countriesQuery.data ?? []).find((row) => row.id === countryId);
    const bounds = computeYearBounds(country ? [country] : [], country ? [country.id] : []);
    // Down to this country's earliest coin, but never a list of one or two
    // entries: a dictionary that thin is less useful than a plain field.
    const min = Math.min(bounds.min, new Date().getFullYear() - 40);
    const max = Math.max(bounds.max, new Date().getFullYear());
    return buildYearList({ min, max }).reverse().map(String);
  }, [countriesQuery.data, countryId]);

  const set = (key: keyof CoinFields) => (value: string) => onChange(key, value);

  return (
    <section className={styles.block} aria-label={t('add.aboutCoin')}>
      <h3 className={styles.title}>{t('add.aboutCoin')}</h3>
      <p className={styles.lead}>{t('add.aboutCoinLead')}</p>

      {onPickPhoto ? (
        <div className={photoStyles.photos}>
          {(['obverse', 'reverse'] as const).map((side) => {
            const preview = photos?.[side];
            return (
              <figure key={side} className={photoStyles.photo}>
                <div className={photoStyles.photoFrame}>
                  {preview ? (
                    <>
                      <img src={preview} alt="" className={styles.photoPreview} />
                      <button
                        type="button"
                        className={photoStyles.photoOverlay}
                        onClick={() => onPickPhoto(side)}
                      >
                        <Pencil size={16} aria-hidden="true" />
                        {t('card.changePhoto')}
                      </button>
                      <button
                        type="button"
                        className={photoStyles.photoEdit}
                        aria-label={t('card.changePhoto')}
                        onClick={() => onPickPhoto(side)}
                      >
                        <Pencil size={13} aria-hidden="true" />
                      </button>
                      {onRemovePhoto ? (
                        <button
                          type="button"
                          className={photoStyles.photoRemove}
                          aria-label={t('collectionPhoto.removePhoto')}
                          onClick={() => onRemovePhoto(side)}
                        >
                          <X size={12} aria-hidden="true" />
                        </button>
                      ) : null}
                    </>
                  ) : (
                    <button
                      type="button"
                      className={styles.photoPlaceholder}
                      onClick={() => onPickPhoto(side)}
                    >
                      <Plus size={20} aria-hidden="true" />
                      {t('add.addPhoto')}
                    </button>
                  )}
                </div>
                <figcaption className={photoStyles.photoLabel}>
                  {t(side === 'obverse' ? 'card.obverse' : 'card.reverse')}
                </figcaption>
              </figure>
            );
          })}
        </div>
      ) : null}

      <FormRow>
        {/* The same field the catalog's "Рік від/до" filters use: a list to
            pick from, free typing for anything older than it offers. Newest
            first here, unlike the filters — a coin you just bought is far
            likelier to be recent than to be from the bottom of the range. */}
        <Combobox
          label={t('add.year')}
          required
          inputMode="numeric"
          placeholder="2021"
          options={yearOptions}
          value={values.issueYear}
          onChange={(event) => set('issueYear')(event.target.value)}
          error={errors.issueYear}
          maxLength={4}
        />
        {/* The denominations dictionary is seeded from what the catalogue
            holds, so for most issuers it offers nothing — which is why this
            is a combobox and not a select (docs/04-business-rules.md, §14). */}
        <Combobox
          label={t('add.denomination')}
          placeholder={t('add.denominationPlaceholder')}
          hint={denominations.length > 0 ? undefined : t('add.noDenominations')}
          options={denominations.map((denomination) => denomination.label)}
          value={values.denomination}
          onChange={(event) => set('denomination')(event.target.value)}
          maxLength={200}
        />
      </FormRow>

      <FormRow>
        {/* Picking an existing series links to the shared record — only an
            admin creates those (docs/04-business-rules.md, rule 2). A name
            typed instead is kept as text: it shows on the card and counts
            towards nothing, which is what the hint says. */}
        <Combobox
          label={t('add.series')}
          placeholder={t('add.seriesPlaceholder')}
          hint={t('add.seriesHint')}
          options={series.map((item) => item.name)}
          value={values.series}
          onChange={(event) => set('series')(event.target.value)}
          maxLength={200}
        />
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
          {/* One field, not the three named catalogues the pipeline fills:
              a collector has a number, not a numbering system (owner,
              2026-09-14). */}
          <Input
            label={t('add.catalogNumber')}
            hint={t('add.catalogNumberHint')}
            maxLength={100}
            value={values.catalogNumber}
            onChange={(event) => set('catalogNumber')(event.target.value)}
          />
        </FormRow>
        {/* The three parts the catalogue's own descriptions are split into
            (docs/02-data-model.md) — the coin itself, then each side. */}
        <Textarea
          label={t('add.description')}
          hint={t('add.descriptionHint')}
          maxLength={4000}
          value={values.description}
          onChange={(event) => set('description')(event.target.value)}
        />
        <Textarea
          label={t('add.descriptionObverse')}
          maxLength={4000}
          value={values.descriptionObverse}
          onChange={(event) => set('descriptionObverse')(event.target.value)}
        />
        <Textarea
          label={t('add.descriptionReverse')}
          maxLength={4000}
          value={values.descriptionReverse}
          onChange={(event) => set('descriptionReverse')(event.target.value)}
        />
      </div>
    </section>
  );
}
