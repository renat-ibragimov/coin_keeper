import { Coffee, Headphones } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import styles from './SiteFooter.module.css';
import { useSupportLink } from './useSupportLink';

interface SiteFooterProps {
  reserveMobileNav?: boolean;
}

export function SiteFooter({ reserveMobileNav = false }: SiteFooterProps) {
  const { t } = useTranslation();
  const { openSupport, openingSupport } = useSupportLink();
  const year = new Date().getFullYear();

  return (
    <footer
      className={[styles.footer, reserveMobileNav ? styles.withMobileNav : ''].join(' ').trim()}
    >
      <span className={styles.madeInUkraine}>
        {t('footer.madeInUkraine')}
        <span role="img" aria-label={t('footer.ukraineFlag')}>
          🇺🇦
        </span>
      </span>
      <span className={styles.copyright}>
        © {year} {t('brand.name')}
      </span>
      <nav className={styles.links} aria-label={t('footer.linksLabel')}>
        <button
          type="button"
          className={styles.link}
          onClick={() => void openSupport()}
          disabled={openingSupport}
        >
          <Headphones size={14} strokeWidth={1.8} aria-hidden="true" />
          {t('footer.support')}
        </button>
        <a className={styles.link} aria-disabled="true">
          <Coffee size={14} strokeWidth={1.8} aria-hidden="true" />
          {t('footer.donate')}
        </a>
      </nav>
    </footer>
  );
}
