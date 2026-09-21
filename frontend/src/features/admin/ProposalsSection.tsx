import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import {
  Button,
  Card,
  DataTable,
  EmptyState,
  ErrorState,
  Pagination,
  Skeleton,
  useToast,
} from '@/shared/ui';

import { approveAdminProposal, fetchAdminProposals, rejectAdminProposal } from './api';

export function ProposalsSection({
  page,
  onPageChange,
}: {
  page: number;
  onPageChange: (page: number) => void;
}) {
  const { t } = useTranslation();
  const client = useQueryClient();
  const toast = useToast();
  const query = useQuery({
    queryKey: ['admin-proposals', page],
    queryFn: () => fetchAdminProposals(page),
  });
  const refresh = async () => client.invalidateQueries({ queryKey: ['admin-proposals'] });
  const approve = useMutation({
    mutationFn: approveAdminProposal,
    onSuccess: async () => {
      await refresh();
      toast.show(t('admin.proposals.approved'));
    },
    onError: () => toast.show(t('admin.proposals.failed'), 'error'),
  });
  const reject = useMutation({
    mutationFn: (id: number) => rejectAdminProposal(id, t('admin.proposals.rejectionReason')),
    onSuccess: async () => {
      await refresh();
      toast.show(t('admin.proposals.rejected'));
    },
    onError: () => toast.show(t('admin.proposals.failed'), 'error'),
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
    <Card variant="panel">
      <DataTable minWidth={700}>
        <thead>
          <tr>
            <th>{t('admin.proposals.coin')}</th>
            <th>{t('admin.proposals.year')}</th>
            <th>{t('admin.proposals.actions')}</th>
          </tr>
        </thead>
        <tbody>
          {query.data.items.map(({ card }) => (
            <tr key={card.id}>
              <td>
                <Link to={`/catalog/${card.id}`}>{card.title}</Link>
                <div>{card.seriesName ?? '—'}</div>
              </td>
              <td>{card.year}</td>
              <td>
                <Button size="sm" onClick={() => approve.mutate(card.id)}>
                  {t('admin.proposals.approve')}
                </Button>{' '}
                <Button size="sm" variant="danger" onClick={() => reject.mutate(card.id)}>
                  {t('admin.proposals.reject')}
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </DataTable>
      <Pagination
        page={query.data.page}
        pageCount={Math.ceil(query.data.total / query.data.pageSize)}
        onChange={onPageChange}
      />
    </Card>
  );
}
