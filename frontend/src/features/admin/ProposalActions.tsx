import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Pencil } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import type { CatalogCard, CatalogItemUpdate } from '@/shared/api/types';
import type { CoinSide } from '@/features/collection/SelectedCoin';
import { Button, ConfirmDialog, useToast } from '@/shared/ui';

import {
  approveAdminProposal,
  deleteAdminProposalPhoto,
  fetchAdminProposal,
  rejectAdminProposal,
  updateAdminProposal,
  uploadAdminProposalPhoto,
} from './api';
import { ProposalEditor } from './ProposalEditor';
import styles from './ProposalActions.module.css';

type PhotoEdit = { kind: 'replace'; blob: Blob; url: string } | { kind: 'remove' };

export function ProposalActions({ card }: { card: CatalogCard }) {
  const { t } = useTranslation();
  const toast = useToast();
  const navigate = useNavigate();
  const client = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [confirmReject, setConfirmReject] = useState(false);
  const query = useQuery({
    queryKey: ['admin-proposal', card.id],
    queryFn: () => fetchAdminProposal(card.id),
    retry: false,
  });
  const finish = async (message: string) => {
    await client.invalidateQueries({ queryKey: ['admin-proposals'] });
    await client.invalidateQueries({ queryKey: ['catalog'] });
    toast.show(message);
    navigate('/admin?section=proposals');
  };
  const approve = useMutation({
    mutationFn: () => approveAdminProposal(card.id),
    onSuccess: () => finish(t('admin.proposals.approved')),
    onError: () => toast.show(t('admin.proposals.failed'), 'error'),
  });
  const reject = useMutation({
    mutationFn: () => rejectAdminProposal(card.id, t('admin.proposals.rejectionReason')),
    onSuccess: () => finish(t('admin.proposals.rejected')),
    onError: () => toast.show(t('admin.proposals.failed'), 'error'),
  });
  const edit = useMutation({
    mutationFn: async ({
      body,
      photos,
    }: {
      body: CatalogItemUpdate;
      photos: Partial<Record<CoinSide, PhotoEdit>>;
    }) => {
      await updateAdminProposal(card.id, body);
      for (const [side, change] of Object.entries(photos) as [CoinSide, PhotoEdit][]) {
        if (change.kind === 'replace') await uploadAdminProposalPhoto(card.id, side, change.blob);
        else await deleteAdminProposalPhoto(card.id, side);
      }
      return approveAdminProposal(card.id);
    },
    onSuccess: () => finish(t('admin.proposals.approved')),
    onError: () => toast.show(t('admin.proposals.failed'), 'error'),
  });
  if (!query.data || query.data.status !== 'draft') return null;
  const busy = approve.isPending || reject.isPending || edit.isPending;
  return (
    <>
      <div className={styles.bar}>
        <strong>{t('admin.proposals.reviewNotice')}</strong>
        <div className={styles.actions}>
          <Button onClick={() => approve.mutate()} loading={approve.isPending} disabled={busy}>
            {t('admin.proposals.approve')}
          </Button>
          <Button variant="danger" onClick={() => setConfirmReject(true)} disabled={busy}>
            {t('admin.proposals.reject')}
          </Button>
          <Button variant="secondary" onClick={() => setEditing(true)} disabled={busy}>
            <Pencil size={15} />
            {t('admin.proposals.edit')}
          </Button>
        </div>
      </div>
      {editing ? (
        <ProposalEditor
          card={query.data.card}
          open
          busy={edit.isPending}
          onCancel={() => setEditing(false)}
          onApprove={(body, photos) => edit.mutate({ body, photos })}
        />
      ) : null}
      <ConfirmDialog
        open={confirmReject}
        title={t('admin.proposals.rejectTitle')}
        confirmLabel={t('admin.proposals.reject')}
        danger
        busy={reject.isPending}
        onCancel={() => setConfirmReject(false)}
        onConfirm={() => reject.mutate()}
      >
        {t('admin.proposals.rejectText')}
      </ConfirmDialog>
    </>
  );
}
