import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Send } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Badge, Button, Card, Skeleton, useToast } from '@/shared/ui';

import { createTelegramLink, fetchTelegramStatus, unlinkTelegram } from './api';
import styles from './TelegramCard.module.css';

/** While waiting for Start to be pressed, ask the server now and then: the
 *  browser has no way of hearing about it, the chat talks to the webhook. */
const POLL_MS = 3000;

export function TelegramCard() {
  const { t } = useTranslation();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [awaiting, setAwaiting] = useState(false);

  const status = useQuery({
    queryKey: ['admin-telegram'],
    queryFn: fetchTelegramStatus,
    refetchInterval: awaiting ? POLL_MS : false,
  });

  const connected = status.data?.connected ?? false;

  // The chat connects itself through the webhook, so the good news arrives in
  // a poll rather than in a mutation's response.
  useEffect(() => {
    if (!awaiting || !connected) return;
    setAwaiting(false);
    toast.show(t('admin.telegram.connected'));
  }, [awaiting, connected, t, toast]);

  const link = useMutation({
    mutationFn: createTelegramLink,
    onSuccess: (data) => {
      setAwaiting(true);
      window.open(data.url, '_blank', 'noopener');
    },
    onError: () => toast.show(t('admin.telegram.linkFailed'), 'error'),
  });

  const unlink = useMutation({
    mutationFn: unlinkTelegram,
    onSuccess: async () => {
      setAwaiting(false);
      await queryClient.invalidateQueries({ queryKey: ['admin-telegram'] });
      toast.show(t('admin.telegram.disconnected'));
    },
  });

  return (
    <Card variant="panel">
      <div className={styles.head}>
        <h2 className={styles.title}>
          <Send size={18} strokeWidth={1.75} aria-hidden="true" />
          {t('admin.telegram.title')}
        </h2>
        {status.isPending ? null : (
          <Badge tone={connected ? 'success' : 'neutral'}>
            {connected ? t('admin.telegram.on') : t('admin.telegram.off')}
          </Badge>
        )}
      </div>

      {status.isPending ? (
        <Skeleton height={48} />
      ) : (
        <>
          <p className={styles.text}>
            {connected ? t('admin.telegram.textOn') : t('admin.telegram.textOff')}
          </p>
          {awaiting && !connected ? (
            <p className={styles.waiting}>{t('admin.telegram.waiting')}</p>
          ) : null}
          <div className={styles.actions}>
            {connected ? (
              <Button
                variant="secondary"
                onClick={() => unlink.mutate()}
                disabled={unlink.isPending}
              >
                {t('admin.telegram.disconnect')}
              </Button>
            ) : (
              <Button onClick={() => link.mutate()} disabled={link.isPending}>
                {t('admin.telegram.connect')}
              </Button>
            )}
          </div>
        </>
      )}
    </Card>
  );
}
