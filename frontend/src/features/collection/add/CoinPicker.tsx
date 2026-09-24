import { useQuery } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { fetchCountries, lookupCatalog } from '@/features/catalog/api';
import type { CatalogListItem } from '@/shared/api/types';
import { coinTitle } from '@/shared/lib/coinTitle';
import { useDismissable } from '@/shared/lib/useDismissable';
import { Badge, CoinImage, Input, Select, Spinner } from '@/shared/ui';

import styles from './CoinPicker.module.css';

/** Below this the suggestion list stays closed: one letter matches half a country. */
const MIN_QUERY = 2;
const DEBOUNCE_MS = 300;

interface CoinPickerProps {
  /**
   * The country field, when the form needs one. Omitted — as the expense
   * branch omits it — the select is not rendered and the search runs across
   * every issuer (owner, 2026-09-14).
   */
  countryId?: number | null;
  onCountryChange?: (countryId: number | null) => void;
  title: string;
  onTitleChange: (title: string) => void;
  onSelect: (item: CatalogListItem) => void;
  /** Shown under the name field; the purchase branch explains what a new name means. */
  titleHint?: string;
  titleError?: string;
  countryError?: string;
  /** Label over the name field — "Назва монети" or, for an expense, the coin it is about. */
  titleLabel: string;
  autoFocusTitle?: boolean;
}

/**
 * A coin's name with live suggestions, optionally narrowed to one country.
 *
 * The purchase branch asks for the country first, and the order is the point
 * (docs/ui.md): a name means nothing on its own — half the world has
 * a coin called "10" — and the country is also what the new personal item
 * will be filed under. Pointing an expense at a coin needs none of that:
 * there the collector types the name of a coin they already own, so the
 * field stands alone and the search covers everything visible to them.
 */
export function CoinPicker({
  countryId = null,
  onCountryChange,
  title,
  onTitleChange,
  onSelect,
  titleHint,
  titleError,
  countryError,
  titleLabel,
  autoFocusTitle,
}: CoinPickerProps) {
  const { t, i18n } = useTranslation();
  const [query, setQuery] = useState('');
  const [listOpen, setListOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  useDismissable(listOpen, () => setListOpen(false), { inside: [root], routeChange: false });

  // Every issuer there has ever been, not just the storefront's active ones:
  // a personal item may be a coin of any of them (docs/business-rules.md).
  const countriesQuery = useQuery({
    queryKey: ['countries', 'all'],
    queryFn: () => fetchCountries('all'),
    staleTime: Infinity,
    enabled: onCountryChange !== undefined,
  });

  useEffect(() => {
    const timer = setTimeout(() => setQuery(title.trim()), DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [title]);

  const enabled = query.length >= MIN_QUERY;
  const results = useQuery({
    queryKey: ['catalog', 'lookup', countryId, query],
    queryFn: () => lookupCatalog(query, countryId ?? undefined),
    enabled,
  });

  const showList = listOpen && enabled;

  return (
    <div className={styles.picker} ref={root}>
      {onCountryChange ? (
        <Select
          label={t('add.country')}
          searchable
          searchPlaceholder={t('add.countrySearch')}
          value={countryId === null ? '' : String(countryId)}
          error={countryError}
          onChange={(event) => {
            const next = event.target.value;
            onCountryChange(next ? Number(next) : null);
          }}
        >
          <option value="">{t('add.countryNone')}</option>
          {(countriesQuery.data ?? []).map((country) => (
            <option key={country.id} value={String(country.id)}>
              {country.name}
            </option>
          ))}
        </Select>
      ) : null}

      {/* A plain text field, not type="search": Chrome clears a search input
          on Escape, and here the value is the coin's name being typed, not a
          query to be thrown away. */}
      <div className={styles.titleField}>
        <Input
          autoFocus={autoFocusTitle}
          label={titleLabel}
          hint={titleHint}
          error={titleError}
          placeholder={t('add.titlePlaceholder')}
          value={title}
          maxLength={500}
          onFocus={() => setListOpen(true)}
          onChange={(event) => {
            onTitleChange(event.target.value);
            setListOpen(true);
          }}
          aria-controls="coin-picker-results"
          aria-expanded={showList}
        />
        {showList ? (
          <div id="coin-picker-results" className={styles.results} role="listbox">
            {results.isPending ? (
              <div className={styles.status}>
                <Spinner size={18} />
              </div>
            ) : null}
            {results.data && results.data.length === 0 ? (
              <div className={styles.status}>{t('add.noMatches')}</div>
            ) : null}
            {results.data?.map((item) => (
              <button
                key={item.id}
                type="button"
                role="option"
                aria-selected={false}
                className={styles.result}
                onClick={() => {
                  setListOpen(false);
                  onSelect(item);
                }}
              >
                <CoinImage src={item.thumbnailUrl} alt="" className={styles.thumb} />
                <span className={styles.resultBody}>
                  <span className={styles.resultTitle}>{coinTitle(item, i18n.language)}</span>
                  <span className={styles.resultMeta}>
                    {[item.country, String(item.year), item.denomination?.label]
                      .filter(Boolean)
                      .join(' · ')}
                  </span>
                </span>
                <span className={styles.resultBadges}>
                  {item.isOwn ? <Badge tone="accent">{t('catalog.badgeOwn')}</Badge> : null}
                  {item.quantityOwned > 0 ? (
                    <Badge tone="success">{t('catalog.badgeInCollection')}</Badge>
                  ) : null}
                </span>
              </button>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}
