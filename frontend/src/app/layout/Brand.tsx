import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { useTheme } from '@/shared/theme/useTheme';

import styles from './Brand.module.css';

interface BrandProps {
  /** `header` fits the app header; `hero` is the larger auth-screen size. */
  size?: 'header' | 'hero';
  /** Where the logo leads; the overview by default. */
  to?: string;
}

/**
 * The full logo (shield + wordmark) on every screen size — one brand
 * everywhere; the monogram is only used for favicons and PWA icons. Assets
 * are derived from public/brand/*.src.png by scripts/build-brand.py; the dark
 * theme gets its own wordmark file with the letters lifted to cream.
 */
export function Brand({ size = 'header', to = '/' }: BrandProps) {
  const { t } = useTranslation();
  const { theme } = useTheme();
  const name = t('brand.name');
  const stem = theme === 'dark' ? '/brand/logo-full-dark' : '/brand/logo-full';
  return (
    <Link to={to} className={[styles.brand, styles[size]].join(' ')} aria-label={name}>
      <picture className={styles.full}>
        <source
          type="image/webp"
          srcSet={`${stem}-400.webp 400w, ${stem}-800.webp 800w, ${stem}-1600.webp 1600w`}
          sizes="(max-width: 900px) 120px, 190px"
        />
        <img
          className={styles.fullImage}
          src={`${stem}-800.png`}
          srcSet={`${stem}-400.png 400w, ${stem}-800.png 800w, ${stem}-1600.png 1600w`}
          sizes="(max-width: 900px) 120px, 190px"
          width="800"
          height="328"
          alt={name}
          decoding="async"
          fetchPriority="high"
        />
      </picture>
    </Link>
  );
}
