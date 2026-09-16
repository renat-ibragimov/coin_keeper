import { Coffee, Headphones } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import styles from './SiteFooter.module.css';
import { useDonationDialog } from './donationDialogContext';
import { useSupportLink } from './useSupportLink';

interface SiteFooterProps {
  reserveMobileNav?: boolean;
}

export function SiteFooter({ reserveMobileNav = false }: SiteFooterProps) {
  const { t } = useTranslation();
  const { openSupport, openingSupport } = useSupportLink();
  const openDonation = useDonationDialog();
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
        <Link to="/privacy" className={styles.link}>
          {t('footer.privacy')}
        </Link>
        <Link to="/terms" className={styles.link}>
          {t('footer.terms')}
        </Link>
        <button
          type="button"
          className={styles.link}
          onClick={() => void openSupport()}
          disabled={openingSupport}
        >
          <Headphones size={14} strokeWidth={1.8} aria-hidden="true" />
          {t('footer.support')}
        </button>
        <button type="button" className={styles.link} onClick={openDonation}>
          <Coffee size={14} strokeWidth={1.8} aria-hidden="true" />
          {t('footer.donate')}
        </button>
      </nav>
    </footer>
  );
}
