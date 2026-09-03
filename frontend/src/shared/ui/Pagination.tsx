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
  return (
    <nav className={styles.pagination} aria-label={t('pagination.label')}>
      <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => onChange(page - 1)}>
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
            onClick={() => onChange(item)}
          >
            {item}
          </button>
        ),
      )}
      <Button
        variant="secondary"
        size="sm"
        disabled={page >= pageCount}
        onClick={() => onChange(page + 1)}
      >
        {t('pagination.next')} →
      </Button>
    </nav>
  );
}
