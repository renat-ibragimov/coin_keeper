import { useTranslation } from 'react-i18next';

import styles from './Brand.module.css';

export function Brand() {
  const { t } = useTranslation();
  return (
    <span className={styles.brand}>
      <svg className={styles.mark} viewBox="0 0 40 40" aria-hidden="true">
        <defs>
          <linearGradient id="ck-gold" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#d8b46a" />
            <stop offset="1" stopColor="#8a6a35" />
          </linearGradient>
        </defs>
        <circle cx="20" cy="20" r="18" fill="url(#ck-gold)" />
        <circle cx="20" cy="20" r="14.5" fill="none" stroke="#fdf6e5" strokeWidth="1.2" />
        <text
          x="20"
          y="26"
          textAnchor="middle"
          fontFamily="Playfair Display, Georgia, serif"
          fontSize="14"
          fontWeight="700"
          fill="#fdf6e5"
        >
          CK
        </text>
      </svg>
      <span className={styles.text}>
        <span className={styles.name}>{t('brand.name')}</span>
        <span className={styles.by}>{t('brand.by')}</span>
      </span>
    </span>
  );
}
