import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { useTheme } from '@/shared/theme/useTheme';

import styles from './Brand.module.css';

interface BrandProps {
  /**
   * `auto` — the full logo on wide screens, the monogram with the name on
   * phones (the app header); `full` — always the full logo (auth screens).
   */
  variant?: 'auto' | 'full';
  /** Where the logo leads; the overview by default. */
  to?: string;
}

/**
 * The brand assets are derived from public/brand/*.src.png by
 * scripts/build-brand.py. The dark theme gets its own wordmark file with the
 * letters lifted to cream — the source ones are dark brown.
 */
export function Brand({ variant = 'auto', to = '/' }: BrandProps) {
  const { t } = useTranslation();
  const { theme } = useTheme();
  const name = t('brand.name');
  const stem = theme === 'dark' ? '/brand/logo-full-dark' : '/brand/logo-full';
  return (
    <Link to={to} className={[styles.brand, styles[variant]].join(' ')} aria-label={name}>
      <picture className={styles.full}>
        <source
          type="image/webp"
          srcSet={`${stem}-400.webp 400w, ${stem}-800.webp 800w, ${stem}-1600.webp 1600w`}
          sizes="(max-width: 900px) 160px, 190px"
        />
        <img
          className={styles.fullImage}
          src={`${stem}-800.png`}
          srcSet={`${stem}-400.png 400w, ${stem}-800.png 800w, ${stem}-1600.png 1600w`}
          sizes="(max-width: 900px) 160px, 190px"
          width="800"
          height="328"
          alt={name}
          decoding="async"
          fetchPriority="high"
        />
      </picture>
      <span className={styles.compact}>
        <picture>
          <source
            type="image/webp"
            srcSet="/brand/logo-mark-128.webp 1x, /brand/logo-mark-256.webp 2x"
          />
          <img
            className={styles.mark}
            src="/brand/logo-mark-128.png"
            srcSet="/brand/logo-mark-128.png 1x, /brand/logo-mark-256.png 2x"
            width="128"
            height="128"
            alt=""
            decoding="async"
          />
        </picture>
        <span className={styles.name}>{name}</span>
      </span>
    </Link>
  );
}
