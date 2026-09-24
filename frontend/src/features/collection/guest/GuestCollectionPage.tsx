import { useTranslation } from 'react-i18next';

import onboardingStyles from '@/features/collection/onboarding/CollectionOnboarding.module.css';
import { useAuthDialog } from '@/features/auth/authDialogContext';
import { Button, PageHeader } from '@/shared/ui';
import styles from './GuestCollectionPage.module.css';

import { CollectionOnboarding } from '../onboarding/CollectionOnboarding';
import type { CollectionSection } from '../onboarding/CollectionOnboarding';

const sections = {
  dashboard: {
    heading: 'dashboard.title',
    subtitle: 'dashboard.subtitle',
  },
  coins: {
    heading: 'collection.title',
    subtitle: 'collection.subtitle',
  },
  completeness: {
    heading: 'completeness.title',
    subtitle: 'completeness.subtitle',
  },
  money: {
    heading: 'expenses.title',
    subtitle: 'expenses.subtitle',
  },
} as const;

export function GuestCollectionPage({ section = 'dashboard' }: { section?: CollectionSection }) {
  const { t } = useTranslation();
  const openAuth = useAuthDialog();
  const content = sections[section];

  return (
    <div className={`${styles.page} ${onboardingStyles.page}`}>
      <PageHeader align="center" title={t(content.heading)} subtitle={t(content.subtitle)} />
      <CollectionOnboarding
        section={section}
        actions={<Button onClick={() => openAuth()}>{t('guest.login')}</Button>}
      />
    </div>
  );
}
