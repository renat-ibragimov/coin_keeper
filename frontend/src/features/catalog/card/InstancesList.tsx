import type { TFunction } from 'i18next';
import { Pencil, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate } from 'react-router-dom';

import { DeleteInstanceDialog } from '@/features/collection/DeleteInstanceDialog';
import type { CatalogCollectionItem } from '@/shared/api/types';
import {
  currencySymbol,
  formatDate,
  formatNumber,
  formatSignedPercent,
  formatSignedUah,
  formatUah,
} from '@/shared/lib/format';
import { Badge, Button, CoinImage, EmptyState, Skeleton } from '@/shared/ui';

import type { SecondaryCurrency } from '@/shared/lib/secondaryAmount';
import {
  formatSecondary,
  formatSecondarySigned,
  pickSecondary,
  toSecondary,
} from '@/shared/lib/secondaryAmount';
import styles from './InstancesList.module.css';

interface InstancePhoto {
  src?: string | null;
  srcSet?: string;
}

interface InstancesListProps {
  items: CatalogCollectionItem[] | undefined;
  loading: boolean;
  /** Where the "add to collection" CTA in the empty state should lead. */
  addHref: string;
  /** The coin's own title, for the delete-confirmation text — instances
   *  carry no title of their own (docs/03-api-contract.md). */
  coinTitle: string;
  /** The catalog item's own obverse photo — instances have no photo of their
   *  own yet, so every row shows the same coin picture. */
  photo: InstancePhoto;
  /** The catalog item's current market price, same for every instance. */
  currentPriceUah: string | null;
  /** Which currency the ≈ figures convert to (settings.secondaryCurrency). */
  secondaryCurrency: SecondaryCurrency;
  /** The live NBU rate for that currency (bootstrap's exchangeRates) — only
   *  for a row's current value, which has no purchase date of its own to
   *  convert by. Its purchase total uses item.totalUsd/totalEur instead, the
   *  backend's own historical-rate conversion. null renders "no data". */
  secondaryRate: number | null;
  /** The viewer's own accounting preference (settings.includeSupportingExpenses,
   *  default on) — whether a row's "Зміна" is measured against its full price
   *  (coin + supporting) or the coin price alone. The three price columns
   *  themselves always show the same breakdown regardless. */
  includeSupportingExpenses: boolean;
}

/** "Скільки часу монета вже в колекції" — the single largest whole unit, not
 *  a precise calendar breakdown: "2 роки" reads better here than "2 роки 3
 *  місяці 12 днів" for a table cell. */
function ownershipDuration(acquisitionDate: string | null, t: TFunction): string {
  if (!acquisitionDate) return '—';
  const start = new Date(`${acquisitionDate}T00:00:00`);
  if (Number.isNaN(start.getTime())) return '—';
  const days = Math.floor((Date.now() - start.getTime()) / (1000 * 60 * 60 * 24));
  if (days < 1) return t('card.durationToday');
  if (days >= 365) return t('card.durationYears', { count: Math.floor(days / 365) });
  if (days >= 30) return t('card.durationMonths', { count: Math.floor(days / 30) });
  return t('card.durationDays', { count: days });
}

/** "Мої екземпляри": one row per purchase of the current user, as a table. */
export function InstancesList({
  items,
  loading,
  addHref,
  coinTitle,
  photo,
  currentPriceUah,
  secondaryCurrency,
  secondaryRate,
  includeSupportingExpenses,
}: InstancesListProps) {
  const { t, i18n } = useTranslation();
  const locale = i18n.language;
  const navigate = useNavigate();
  const [deleting, setDeleting] = useState<CatalogCollectionItem | null>(null);

  if (loading) {
    return (
      <div className={styles.list} aria-busy="true">
        <Skeleton height={64} />
        <Skeleton height={64} />
      </div>
    );
  }
  if (!items || items.length === 0) {
    return (
      <EmptyState
        title={t('card.instancesEmpty')}
        actions={
          <Link to={addHref}>
            <Button variant="secondary">{t('catalog.addToCollection')}</Button>
          </Link>
        }
      />
    );
  }

  const currentPrice = currentPriceUah !== null ? Number(currentPriceUah) : null;
  const symbol = currencySymbol(secondaryCurrency);
  const approxText = (value: string | null) =>
    value !== null ? t('card.approxSecondary', { value, symbol }) : t('dashboard.rateMissing');

  return (
    <>
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col">
                <span className={styles.srOnly}>{t('card.instancePhoto')}</span>
              </th>
              <th scope="col">{t('card.instanceGrade')}</th>
              <th scope="col">{t('card.quantity')}</th>
              <th scope="col">{t('card.instanceSeller')}</th>
              <th scope="col" className={styles.narrowHeader}>
                {t('card.instancePrice')}
              </th>
              <th scope="col" className={styles.narrowHeader}>
                {t('card.instanceExtraExpenses')}
              </th>
              <th scope="col">{t('card.instanceFullPrice')}</th>
              <th scope="col">{t('card.instanceCurrentPrice')}</th>
              <th scope="col">{t('card.instanceChange')}</th>
              <th scope="col">{t('card.instanceDate')}</th>
              <th scope="col">{t('card.instanceOwnedFor')}</th>
              <th scope="col">{t('card.instanceStorage')}</th>
              <th scope="col" className={styles.notesHeader}>
                {t('card.instanceNotes')}
              </th>
              <th scope="col">
                <span className={styles.srOnly}>{t('common.actions')}</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => {
              const foreign = item.purchaseCurrency !== null && item.purchaseCurrency !== 'UAH';
              const rate = foreign ? formatNumber(item.purchaseRateUah, locale, 4) : null;
              const coinTotal = Number(item.totalUah);
              const extraExpenses =
                item.supportingExpensesUah !== null ? Number(item.supportingExpensesUah) : null;
              // "Повна ціна" is always coin + extra, a factual breakdown —
              // unlike `changeBasis` below, it does not depend on the
              // viewer's include/exclude preference.
              const fullTotal = extraExpenses !== null ? coinTotal + extraExpenses : coinTotal;
              const changeBasis = includeSupportingExpenses ? fullTotal : coinTotal;
              const rowCurrentValue = currentPrice !== null ? currentPrice * item.quantity : null;
              const change = rowCurrentValue !== null ? rowCurrentValue - changeBasis : null;
              const changePercent =
                change !== null && changeBasis > 0 ? (change / changeBasis) * 100 : null;
              // The backend's own historical-rate conversion (item.totalUsd/
              // totalEur) for what was spent then; the live rate only for a
              // value with no purchase date of its own (see the prop doc above).
              const coinTotalSecondary = pickSecondary(
                item.totalUsd,
                item.totalEur,
                secondaryCurrency,
              );
              const coinTotalApprox =
                coinTotalSecondary !== null ? Number(coinTotalSecondary) : null;
              // No per-currency breakdown exists for a supporting expense
              // (docs/03-api-contract.md) — an accurate ≈ figure exists only
              // when there is nothing to merge in, coin-only or not.
              const fullTotalApprox = extraExpenses === null ? coinTotalApprox : null;
              const changeBasisApprox = includeSupportingExpenses
                ? fullTotalApprox
                : coinTotalApprox;
              const rowCurrentValueApprox =
                rowCurrentValue !== null ? toSecondary(rowCurrentValue, secondaryRate) : null;
              const changeApprox =
                rowCurrentValueApprox !== null && changeBasisApprox !== null
                  ? rowCurrentValueApprox - changeBasisApprox
                  : null;
              const editHref = `/collection/coins/${item.id}/edit`;

              return (
                <tr
                  key={item.id}
                  data-testid="instance-row"
                  className={styles.row}
                  onClick={() => navigate(editHref)}
                >
                  <td className={styles.photoCell}>
                    <CoinImage
                      src={photo.src}
                      srcSet={photo.srcSet}
                      alt=""
                      className={styles.photo}
                    />
                  </td>
                  <td>{item.grade ? <Badge>{item.grade}</Badge> : '—'}</td>
                  <td className="tabular">{item.quantity}</td>
                  <td>{item.seller || '—'}</td>
                  <td className="tabular">
                    <span className={styles.price}>{formatUah(coinTotal, locale) ?? '—'}</span>
                    <span className={styles.secondary}>
                      {approxText(formatSecondary(coinTotalApprox, locale))}
                    </span>
                    {rate ? (
                      <span className={styles.secondary}>
                        {t('card.rateFormat', {
                          rate,
                          symbol: currencySymbol(item.purchaseCurrency),
                        })}
                      </span>
                    ) : null}
                  </td>
                  <td className="tabular">
                    {extraExpenses !== null ? formatUah(extraExpenses, locale) : '—'}
                  </td>
                  <td className="tabular">
                    <span className={styles.price}>{formatUah(fullTotal, locale) ?? '—'}</span>
                  </td>
                  <td className="tabular">
                    {rowCurrentValue !== null ? (
                      <>
                        <span className={styles.price}>{formatUah(rowCurrentValue, locale)}</span>
                        <span className={styles.secondary}>
                          {approxText(formatSecondary(rowCurrentValueApprox, locale))}
                        </span>
                      </>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td className="tabular">
                    {change !== null ? (
                      <>
                        <span
                          className={[
                            styles.price,
                            change > 0 ? styles.positive : change < 0 ? styles.negative : '',
                          ].join(' ')}
                        >
                          {formatSignedUah(change, locale)}
                        </span>
                        {changePercent !== null ? (
                          <span
                            className={[
                              styles.secondary,
                              change > 0 ? styles.positive : change < 0 ? styles.negative : '',
                            ].join(' ')}
                          >
                            {formatSignedPercent(changePercent, locale)}
                          </span>
                        ) : null}
                        {includeSupportingExpenses && extraExpenses !== null ? null : (
                          <span className={styles.secondary}>
                            {approxText(
                              changeApprox !== null
                                ? formatSecondarySigned(changeApprox, locale)
                                : null,
                            )}
                          </span>
                        )}
                      </>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td className="tabular">
                    {item.acquisitionDate ? formatDate(item.acquisitionDate, locale) : '—'}
                  </td>
                  <td className="tabular">{ownershipDuration(item.acquisitionDate, t)}</td>
                  <td>{item.storageLocation || '—'}</td>
                  <td className={styles.notes}>{item.notes || '—'}</td>
                  <td onClick={(event) => event.stopPropagation()}>
                    {/* A plain block td, with the flex row nested inside it —
                        a flex display on the td itself leaves its height
                        driven by its own content instead of the row's
                        tallest cell, so its border-bottom floats above the
                        rest of the row's divider line. */}
                    <div className={styles.actions}>
                      <Link to={editHref} aria-label={t('common.edit')} className={styles.iconLink}>
                        <Button variant="ghost" size="sm" className={styles.iconButton}>
                          <Pencil size={16} aria-hidden="true" />
                        </Button>
                      </Link>
                      <Button
                        variant="ghost"
                        size="sm"
                        className={styles.iconButton}
                        aria-label={t('common.delete')}
                        onClick={() => setDeleting(item)}
                      >
                        <Trash2 size={16} aria-hidden="true" />
                      </Button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <DeleteInstanceDialog
        item={deleting && { id: deleting.id, title: coinTitle, totalUah: deleting.totalUah }}
        onClose={() => setDeleting(null)}
      />
    </>
  );
}
