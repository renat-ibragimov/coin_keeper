import { useTranslation } from 'react-i18next';

import { Button } from './Button';
import { pageItems } from './pageItems';
import styles from './Pagination.module.css';

interface PaginationProps {
  page: number;
  pageCount: number;
  onChange: (page: number) => void;
}

export function Pagination({ page, pageCount, onChange }: PaginationProps) {
  const { t } = useTranslation();
  if (pageCount <= 1) return null;
  // Every page-change goes through here, whatever the caller does with the
  // number (a URL search param or, e.g. SeriesDetailPage, local state) — the
  // page landing at the top of the new results is a property of pagination
  // itself, not something each screen has to remember to wire up
  // (docs/08-ui-map.md).
  const goTo = (next: number) => {
    onChange(next);
    window.scrollTo({ top: 0 });
  };
  return (
    <nav className={styles.pagination} aria-label={t('pagination.label')}>
      <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => goTo(page - 1)}>
        ← {t('pagination.previous')}
      </Button>
      {pageItems(page, pageCount).map((item, index) =>
        item === 'gap' ? (
          <span key={`gap-${index}`} className={styles.ellipsis}>
            …
          </span>
        ) : (
          <button
            key={item}
            type="button"
            className={[styles.page, item === page ? styles.current : ''].join(' ')}
            aria-current={item === page ? 'page' : undefined}
            onClick={() => goTo(item)}
          >
            {item}
          </button>
        ),
      )}
      <Button
        variant="secondary"
        size="sm"
        disabled={page >= pageCount}
        onClick={() => goTo(page + 1)}
      >
        {t('pagination.next')} →
      </Button>
    </nav>
  );
}
