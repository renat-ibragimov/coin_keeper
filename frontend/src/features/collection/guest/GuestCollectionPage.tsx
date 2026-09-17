import { Coins, Layers, LayoutDashboard, Wallet } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { useAuthDialog } from '@/features/auth/authDialogContext';
import { Button, EmptyState, PageHeader } from '@/shared/ui';
import styles from './GuestCollectionPage.module.css';

type Section = 'dashboard' | 'coins' | 'series' | 'money';

const sections = {
  dashboard: {
    heading: 'dashboard.title',
    subtitle: 'dashboard.subtitle',
    title: 'dashboard.emptyTitle',
    description: 'dashboard.emptyText',
    icon: LayoutDashboard,
  },
  coins: {
    heading: 'collection.title',
    subtitle: 'collection.subtitle',
    title: 'collection.emptyTitle',
    description: 'collection.emptyText',
    icon: Coins,
  },
  series: {
    heading: 'series.title',
    subtitle: 'series.subtitle',
    title: 'series.emptyCollectionTitle',
    description: 'series.emptyCollectionText',
    icon: Layers,
  },
  money: {
    heading: 'expenses.title',
    subtitle: 'expenses.subtitle',
    title: 'expenses.emptyCollectionTitle',
    description: 'expenses.emptyCollectionText',
    icon: Wallet,
  },
} as const;

export function GuestCollectionPage({ section = 'dashboard' }: { section?: Section }) {
  const { t } = useTranslation();
  const openAuth = useAuthDialog();
  const content = sections[section];
  const Icon = content.icon;

  return (
    <div className={styles.page}>
      <PageHeader align="center" title={t(content.heading)} subtitle={t(content.subtitle)} />
      <EmptyState
        variant="card"
        icon={<Icon strokeWidth={1.75} />}
        title={t(content.title)}
        description={t(content.description)}
        actions={<Button onClick={() => openAuth()}>{t('guest.login')}</Button>}
      />
    </div>
  );
}
