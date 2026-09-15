import { useTranslation } from 'react-i18next';

import styles from './SiteFooter.module.css';

interface SiteFooterProps {
  reserveMobileNav?: boolean;
}

export function SiteFooter({ reserveMobileNav = false }: SiteFooterProps) {
  const { t } = useTranslation();
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
        <a className={styles.link} aria-disabled="true">
          {t('footer.support')}
        </a>
        <a className={styles.link} aria-disabled="true">
          {t('footer.donate')}
        </a>
      </nav>
    </footer>
  );
}
