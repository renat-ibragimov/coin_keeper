import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Coins, Users } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { useAuth } from '@/features/auth/useAuth';
import {
  Badge,
  Button,
  Card,
  DataTable,
  ErrorState,
  Pagination,
  Skeleton,
  StatTile,
  useToast,
} from '@/shared/ui';

import { fetchAdminUsers, PAGE_SIZE, setAdminUserRole } from './api';
import styles from './UsersSection.module.css';

export function UsersSection({
  page,
  onPageChange,
}: {
  page: number;
  onPageChange: (page: number) => void;
}) {
  const { t, i18n } = useTranslation();
  const { user: currentUser } = useAuth();
  const queryClient = useQueryClient();
  const toast = useToast();
  const query = useQuery({
    queryKey: ['admin-users', page],
    queryFn: () => fetchAdminUsers(page),
  });
  const role = useMutation({
    mutationFn: ({ id, value }: { id: number; value: 'user' | 'admin' }) =>
      setAdminUserRole(id, value),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['admin-users'] });
      toast.show(t('admin.users.roleSaved'));
    },
    onError: () => toast.show(t('admin.users.roleFailed'), 'error'),
  });

  if (query.isPending) return <Skeleton height={260} />;
  if (query.isError) return <ErrorState onRetry={() => void query.refetch()} />;

  const data = query.data;
  return (
    <div className={styles.section}>
      <div className={styles.stats}>
        <StatTile icon={<Users />} label={t('admin.users.total')} value={data.summary.totalUsers} />
        <StatTile
          icon={<Coins />}
          label={t('admin.users.collectors')}
          value={data.summary.collectors}
          hint={t('admin.users.collectorsHint')}
        />
      </div>
      <Card variant="panel">
        <h2 className={styles.title}>{t('admin.users.title')}</h2>
        <DataTable minWidth={760}>
          <thead>
            <tr>
              <th>{t('admin.users.user')}</th>
              <th>{t('admin.users.registered')}</th>
              <th>{t('admin.users.emailStatus')}</th>
              <th>{t('admin.users.coins')}</th>
              <th>{t('admin.users.role')}</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((item) => {
              const isSelf = item.id === currentUser?.id;
              const makeAdmin = item.role !== 'admin';
              const cannotPromote = makeAdmin && (!item.isActive || !item.emailVerified);
              return (
                <tr key={item.id}>
                  <td>
                    <strong>{item.displayName || item.email}</strong>
                    {item.displayName ? <div className={styles.email}>{item.email}</div> : null}
                  </td>
                  <td>
                    {new Intl.DateTimeFormat(i18n.language, { dateStyle: 'medium' }).format(
                      new Date(item.createdAt),
                    )}
                  </td>
                  <td>
                    <Badge tone={item.emailVerified ? 'success' : 'neutral'}>
                      {t(item.emailVerified ? 'admin.users.verified' : 'admin.users.unverified')}
                    </Badge>
                  </td>
                  <td className="tabular">{item.coinCount}</td>
                  <td>
                    <div className={styles.roleCell}>
                      <Badge tone={item.role === 'admin' ? 'success' : 'neutral'}>
                        {t(`admin.users.roles.${item.role}`)}
                      </Badge>
                      <Button
                        size="sm"
                        variant="secondary"
                        disabled={isSelf || cannotPromote || role.isPending}
                        onClick={() =>
                          role.mutate({ id: item.id, value: makeAdmin ? 'admin' : 'user' })
                        }
                      >
                        {t(makeAdmin ? 'admin.users.makeAdmin' : 'admin.users.removeAdmin')}
                      </Button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </DataTable>
        <Pagination
          page={data.page}
          pageCount={Math.ceil(data.total / PAGE_SIZE)}
          onChange={onPageChange}
        />
      </Card>
    </div>
  );
}
