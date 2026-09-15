import { ExternalLink } from 'lucide-react';
import { QRCodeSVG } from 'qrcode.react';
import { useState } from 'react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { DONATION_URL } from '@/shared/config/donation';
import { Modal } from '@/shared/ui';

import styles from './DonationDialog.module.css';
import { DonationDialogContext } from './donationDialogContext';

interface DonationDialogProps {
  open: boolean;
  onClose: () => void;
}

export function DonationDialogProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);

  return (
    <DonationDialogContext.Provider value={() => setOpen(true)}>
      {children}
      <DonationDialog open={open} onClose={() => setOpen(false)} />
    </DonationDialogContext.Provider>
  );
}

export function DonationDialog({ open, onClose }: DonationDialogProps) {
  const { t } = useTranslation();

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={t('donation.title')}
      size="sm"
      mobilePlacement="center"
    >
      <div className={styles.content}>
        <p className={styles.description}>{t('donation.description')}</p>
        <a
          className={styles.primaryAction}
          href={DONATION_URL}
          target="_blank"
          rel="noopener noreferrer"
        >
          {t('donation.openJar')}
          <ExternalLink size={17} aria-hidden="true" />
        </a>
        <div className={styles.separator} aria-hidden="true">
          <span>{t('common.or')}</span>
        </div>
        <div className={styles.qrSection}>
          <div className={styles.qrFrame}>
            <QRCodeSVG
              value={DONATION_URL}
              size={180}
              bgColor="#ffffff"
              fgColor="#000000"
              level="M"
              title={t('donation.qrTitle')}
            />
          </div>
          <p className={styles.qrHint}>{t('donation.scanQr')}</p>
        </div>
      </div>
    </Modal>
  );
}
