import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import { CoinCard } from '@/features/catalog/CoinCard';
import { EmptyState, ErrorState, Pagination, Skeleton } from '@/shared/ui';

import { fetchAdminProposals } from './api';
import styles from './AdminPage.module.css';

export function ProposalsSection({
  page,
  onPageChange,
}: {
  page: number;
  onPageChange: (page: number) => void;
}) {
  const { t } = useTranslation();
  const query = useQuery({
    queryKey: ['admin-proposals', page],
    queryFn: () => fetchAdminProposals(page),
  });
  if (query.isPending) return <Skeleton height={220} />;
  if (query.isError) return <ErrorState onRetry={() => void query.refetch()} />;
  if (query.data.items.length === 0) {
    return (
      <EmptyState
        title={t('admin.proposals.emptyTitle')}
        description={t('admin.proposals.emptyText')}
      />
    );
  }
  return (
    <div>
      <div className={styles.proposalsGrid}>
        {query.data.items.map(({ card }) => (
          <CoinCard key={card.id} item={card} review />
        ))}
      </div>
      <Pagination
        page={query.data.page}
        pageCount={Math.ceil(query.data.total / query.data.pageSize)}
        onChange={onPageChange}
      />
    </div>
  );
}
