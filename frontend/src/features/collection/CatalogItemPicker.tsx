import { useQuery } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { searchCatalog } from '@/features/catalog/api';
import type { CatalogListItem } from '@/shared/api/types';
import { coinTitle } from '@/shared/lib/coinTitle';
import { useDismissable } from '@/shared/lib/useDismissable';
import { Badge, CoinImage, Input, Spinner } from '@/shared/ui';

import styles from './CatalogItemPicker.module.css';

interface CatalogItemPickerProps {
  onSelect: (item: CatalogListItem) => void;
}

/** Inline catalog search with a result list: shared items plus the user's own. */
export function CatalogItemPicker({ onSelect }: CatalogItemPickerProps) {
  const { t } = useTranslation();
  const [text, setText] = useState('');
  const [query, setQuery] = useState('');
  const [listOpen, setListOpen] = useState(true);
  const root = useRef<HTMLDivElement>(null);
  useDismissable(listOpen, () => setListOpen(false), { inside: [root], routeChange: false });

  useEffect(() => {
    const timer = setTimeout(() => setQuery(text.trim()), 300);
    return () => clearTimeout(timer);
  }, [text]);

  const results = useQuery({
    queryKey: ['catalog', 'search', query],
    queryFn: () => searchCatalog(query),
    enabled: query.length >= 2,
  });

  return (
    <div className={styles.picker} ref={root}>
      <Input
        type="search"
        autoFocus
        onFocus={() => setListOpen(true)}
        label={t('purchase.pickTitle')}
        hint={t('purchase.pickHint')}
        placeholder={t('catalog.searchPlaceholder')}
        value={text}
        onChange={(event) => {
          setText(event.target.value);
          setListOpen(true);
        }}
        aria-controls="catalog-picker-results"
        aria-expanded={listOpen && query.length >= 2}
      />
      {listOpen && query.length >= 2 ? (
        <div id="catalog-picker-results" className={styles.results} role="listbox">
          {results.isPending ? (
            <div className={styles.status}>
              <Spinner size={18} />
            </div>
          ) : null}
          {results.data && results.data.items.length === 0 ? (
            <div className={styles.status}>{t('catalog.emptyTitle')}</div>
          ) : null}
          {results.data?.items.map((item) => (
            <button
              key={item.id}
              type="button"
              role="option"
              aria-selected={false}
              className={styles.result}
              onClick={() => onSelect(item)}
            >
              <CoinImage src={item.thumbnailUrl} alt="" className={styles.thumb} />
              <span className={styles.resultBody}>
                <span className={styles.resultTitle}>{coinTitle(item)}</span>
                <span className={styles.resultMeta}>
                  {[item.country, String(item.year), item.denomination].filter(Boolean).join(' · ')}
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
  );
}
