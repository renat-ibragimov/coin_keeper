import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom';

import { fetchAllMaterials, fetchCard, fetchCurrencies } from '@/features/catalog/api';
import { fetchBootstrap } from '@/features/dashboard/api';
import { createExpense, MANUAL_CATEGORIES } from '@/features/expenses/api';
import { ExpenseForm } from '@/features/expenses/ExpenseForm';
import type { ExpenseValues } from '@/features/expenses/ExpenseForm';
import type {
  CatalogListItem,
  CollectionItemCreate,
  ExpenseCategory,
  NewCatalogItem,
} from '@/shared/api/types';
import { parseDecimal } from '@/shared/lib/format';
import { Button, Card, ErrorState, PageHeader, Select, Skeleton, useToast } from '@/shared/ui';

import { createCollectionItem, fetchStorageLocations } from '../api';
import { COLLECTION_DEPENDENT_KEYS } from '../model';
import { PurchaseForm } from '../PurchaseForm';
import type { PurchaseValues } from '../PurchaseForm';
import { SelectedCoin } from '../SelectedCoin';
import styles from './AddPage.module.css';
import { emptyCarried } from './carried';
import type { CarriedValues } from './carried';
import { emptyCoinFields } from './coinFields';
import type { CoinFieldErrors, CoinFields } from './coinFields';
import { CoinPicker } from './CoinPicker';
import { NewCoinFields } from './NewCoinFields';

/** "Покупка монети" plus every category a person records by hand. */
const PURCHASE = 'coin_purchase' as const;
type AddType = typeof PURCHASE | ExpenseCategory;

function parseType(value: string | null): AddType {
  if (value === PURCHASE) return PURCHASE;
  return MANUAL_CATEGORIES.includes(value as ExpenseCategory)
    ? (value as ExpenseCategory)
    : PURCHASE;
}

function positiveInt(value: string | null): number | null {
  const parsed = Number.parseInt(value ?? '', 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function trimmedOrNull(value: string): string | null {
  return value.trim() || null;
}

function decimalOrNull(value: string): string | null {
  const parsed = parseDecimal(value);
  return parsed === null ? null : String(parsed);
}

/**
 * `/collection/add` — one page for everything that costs money.
 *
 * The first field is the type, and it decides what the rest of the form is:
 * a coin purchase (the default) or one of the supporting expenses. The sum,
 * the currency, the date, the seller and the note survive switching between
 * them (`CarriedValues`) — they mean the same thing on both sides, and
 * retyping them is the kind of friction that makes people stop recording
 * things (docs/08-ui-map.md).
 *
 * The purchase branch is the interesting one. A coin is found by country and
 * then by name; picking a suggestion collapses the form into the usual
 * purchase view for that catalog item. Typing a name the catalog does not
 * have opens "Про монету" instead, and the purchase then carries the coin
 * with it in a single request (docs/03-api-contract.md, `newCatalogItem`).
 */
export function AddPage() {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const location = useLocation();
  const toast = useToast();
  const queryClient = useQueryClient();

  const type = parseType(params.get('type'));
  const isPurchase = type === PURCHASE;
  const catalogItemId = positiveInt(params.get('catalogItemId'));

  const [carried, setCarried] = useState<CarriedValues>(emptyCarried);
  const [countryId, setCountryId] = useState<number | null>(null);
  const [title, setTitle] = useState('');
  const [coinFields, setCoinFields] = useState<CoinFields>(emptyCoinFields);
  const [coinErrors, setCoinErrors] = useState<CoinFieldErrors>({});
  const [pickerErrors, setPickerErrors] = useState<{ country?: string; title?: string }>({});

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
  const materialsQuery = useQuery({
    queryKey: ['materials', 'all'],
    queryFn: fetchAllMaterials,
    staleTime: Infinity,
  });

  const from = (location.state as { from?: string } | null)?.from;

  const setType = (next: AddType) => {
    const query = new URLSearchParams(params);
    query.set('type', next);
    // A coin chosen for a purchase is not a coin chosen for an expense: the
    // expense branch links to one, the purchase branch is about one.
    query.delete('catalogItemId');
    setParams(query, { replace: true });
    setPickerErrors({});
  };

  const chooseCoin = (item: CatalogListItem) => {
    const query = new URLSearchParams(params);
    query.set('catalogItemId', String(item.id));
    setParams(query, { replace: true });
    setPickerErrors({});
  };

  const clearCoin = () => {
    const query = new URLSearchParams(params);
    query.delete('catalogItemId');
    setParams(query, { replace: true });
  };

  const purchaseMutation = useMutation({
    mutationFn: (values: PurchaseValues) => createCollectionItem(purchaseBody(values)),
    onSuccess: async (created) => {
      await Promise.all(
        COLLECTION_DEPENDENT_KEYS.map((key) => queryClient.invalidateQueries({ queryKey: [key] })),
      );
      toast.show(t('purchase.created'));
      navigate(from ?? `/catalog/${created.catalogItemId}`, { replace: true });
    },
  });

  const expenseMutation = useMutation({
    mutationFn: (values: ExpenseValues) => createExpense(values),
    onSuccess: async () => {
      await Promise.all(
        ['expenses', 'bootstrap'].map((key) => queryClient.invalidateQueries({ queryKey: [key] })),
      );
      toast.show(t('expenses.created'));
      navigate(from ?? '/collection/money', { replace: true });
    },
  });

  /** Either a reference to a catalog item or the coin itself (docs/03-api-contract.md). */
  function purchaseBody(values: PurchaseValues): CollectionItemCreate {
    if (catalogItemId !== null) return { ...values, catalogItemId };
    return { ...values, newCatalogItem: newCatalogItem() };
  }

  function newCatalogItem(): NewCatalogItem {
    // A name typed into the material field is a dictionary row when it
    // matches one, free text when it does not (docs/03-api-contract.md).
    const typed = coinFields.material.trim();
    const known = (materialsQuery.data ?? []).find(
      (material) => material.name.toLocaleLowerCase() === typed.toLocaleLowerCase(),
    );
    return {
      countryId: countryId!,
      titleOriginal: title.trim(),
      issueYear: Number.parseInt(coinFields.issueYear, 10),
      collectionGroup: coinFields.collectionGroup,
      metalKind: coinFields.metalKind,
      seriesId: positiveInt(coinFields.seriesId),
      denominationId: positiveInt(coinFields.denominationId),
      compositionId: known ? known.id : null,
      material: known ? null : typed,
      mintageAnnounced: positiveInt(coinFields.mintageAnnounced),
      weightGrams: decimalOrNull(coinFields.weightGrams),
      diameterMm: decimalOrNull(coinFields.diameterMm),
      thicknessMm: decimalOrNull(coinFields.thicknessMm),
      edgeTypeId: positiveInt(coinFields.edgeTypeId),
      qualityTypeId: positiveInt(coinFields.qualityTypeId),
      shape: trimmedOrNull(coinFields.shape),
      catalogKm: trimmedOrNull(coinFields.catalogKm),
      catalogUc: trimmedOrNull(coinFields.catalogUc),
      catalogNumista: trimmedOrNull(coinFields.catalogNumista),
      notes: trimmedOrNull(coinFields.notes),
      edge: null,
      quality: null,
      issueDate: null,
    };
  }

  /** Country, name and the three mandatory fields of "Про монету". */
  function validateNewCoin(): boolean {
    const picker: { country?: string; title?: string } = {};
    if (countryId === null) picker.country = t('common.required');
    if (!title.trim()) picker.title = t('common.required');

    const coin: CoinFieldErrors = {};
    const year = Number.parseInt(coinFields.issueYear, 10);
    if (!Number.isInteger(year) || year < 1 || year > 2200) coin.issueYear = t('add.yearInvalid');
    if (!coinFields.material.trim()) coin.material = t('common.required');
    for (const key of ['weightGrams', 'diameterMm', 'thicknessMm'] as const) {
      const value = coinFields[key];
      if (value.trim() && decimalOrNull(value) === null) coin[key] = t('add.numberInvalid');
    }
    if (coinFields.mintageAnnounced.trim() && positiveInt(coinFields.mintageAnnounced) === null) {
      coin.mintageAnnounced = t('add.numberInvalid');
    }

    setPickerErrors(picker);
    setCoinErrors(coin);
    return Object.keys(picker).length === 0 && Object.keys(coin).length === 0;
  }

  const card = cardQuery.data;
  const settings = bootstrapQuery.data?.settings;
  const currencies = currenciesQuery.data ?? [];
  const storageLocations = (storageLocationsQuery.data ?? []).map((location) => location.name);
  const cancel = () => navigate(from ?? (isPurchase ? '/collection/coins' : '/collection/money'));

  const purchaseForm = (key: string, beforeSubmit?: () => boolean) =>
    settings ? (
      <PurchaseForm
        key={key}
        carried={carried}
        onCarriedChange={setCarried}
        beforeSubmit={beforeSubmit}
        defaultGrade={settings.defaultGrade}
        defaultStorageLocation={settings.defaultStorageLocation}
        storageLocations={storageLocations}
        currencies={currencies}
        busy={purchaseMutation.isPending}
        submitError={purchaseMutation.error}
        onSubmit={(values) => purchaseMutation.mutate(values)}
        onCancel={cancel}
      />
    ) : (
      <div className={styles.formSkeleton}>
        <Skeleton height={42} />
        <Skeleton height={42} />
        <Skeleton height={96} />
      </div>
    );

  return (
    <div className={styles.page}>
      <PageHeader
        align="center"
        title={t('add.title')}
        subtitle={isPurchase ? t('add.subtitlePurchase') : t('add.subtitleExpense')}
      />

      <div className={styles.content}>
        {catalogItemId !== null && card ? <SelectedCoin card={card} onChange={clearCoin} /> : null}

        <Card className={styles.form}>
          <div className={styles.stack}>
            <Select
              label={t('add.type')}
              value={type}
              onChange={(event) => setType(event.target.value as AddType)}
            >
              <option value={PURCHASE}>{t('add.typeCoinPurchase')}</option>
              {MANUAL_CATEGORIES.map((category) => (
                <option key={category} value={category}>
                  {t(`expenses.categories.${category}`)}
                </option>
              ))}
            </Select>

            {isPurchase ? (
              catalogItemId !== null ? (
                cardQuery.isError ? (
                  <ErrorState
                    title={t('card.notFoundTitle')}
                    actions={
                      <Button variant="secondary" onClick={clearCoin}>
                        {t('purchase.changeItem')}
                      </Button>
                    }
                  />
                ) : card ? (
                  purchaseForm(`coin-${catalogItemId}`)
                ) : (
                  <Skeleton height={240} />
                )
              ) : (
                <>
                  <CoinPicker
                    countryId={countryId}
                    onCountryChange={(next) => {
                      setCountryId(next);
                      // Series and denominations belong to a country; a
                      // choice made under another one is meaningless here.
                      setCoinFields((current) => ({
                        ...current,
                        seriesId: '',
                        denominationId: '',
                      }));
                    }}
                    title={title}
                    onTitleChange={setTitle}
                    onSelect={chooseCoin}
                    titleLabel={t('add.coinTitle')}
                    titleHint={t('add.coinTitleHint')}
                    titleError={pickerErrors.title}
                    countryError={pickerErrors.country}
                  />
                  {title.trim() ? (
                    <NewCoinFields
                      countryId={countryId}
                      values={coinFields}
                      errors={coinErrors}
                      onChange={(key, value) =>
                        setCoinFields((current) => ({ ...current, [key]: value }))
                      }
                    />
                  ) : null}
                  {purchaseForm('new-coin', validateNewCoin)}
                </>
              )
            ) : (
              <ExpenseForm
                key={`expense-${type}`}
                category={type}
                showCategory={false}
                carried={carried}
                onCarriedChange={setCarried}
                catalogItemId={catalogItemId}
                coinField={
                  <div className={styles.linkedCoin}>
                    <h3 className={styles.linkedTitle}>{t('add.linkedCoin')}</h3>
                    <p className={styles.linkedLead}>{t('add.linkedCoinLead')}</p>
                    {catalogItemId === null ? (
                      <CoinPicker
                        countryId={countryId}
                        onCountryChange={setCountryId}
                        title={title}
                        onTitleChange={setTitle}
                        onSelect={chooseCoin}
                        titleLabel={t('add.coinTitle')}
                        titleHint={t('add.linkedCoinHint')}
                      />
                    ) : null}
                  </div>
                }
                currencies={currencies}
                busy={expenseMutation.isPending}
                submitError={expenseMutation.error}
                onSubmit={(values) => expenseMutation.mutate(values)}
                onCancel={cancel}
              />
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}
