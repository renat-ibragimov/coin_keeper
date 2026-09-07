import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import { formatUah } from '@/shared/lib/format';
import { ConfirmDialog, useToast } from '@/shared/ui';

import { deleteCollectionItem } from './api';
import { COLLECTION_DEPENDENT_KEYS } from './model';

/** The purchase's own title and total — not the full CollectionItemOut, so
 *  a caller with a narrower shape (e.g. a coin card's own instance list,
 *  which already knows the coin's title) can reuse this dialog too. */
interface DeletableInstance {
  id: number;
  title: string;
  totalUah: string;
}

interface DeleteInstanceDialogProps {
  item: DeletableInstance | null;
  onClose: () => void;
  onDeleted?: () => void;
}

export function DeleteInstanceDialog({ item, onClose, onDeleted }: DeleteInstanceDialogProps) {
  const { t, i18n } = useTranslation();
  const toast = useToast();
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: (id: number) => deleteCollectionItem(id),
    onSuccess: async () => {
      await Promise.all(
        COLLECTION_DEPENDENT_KEYS.map((key) => queryClient.invalidateQueries({ queryKey: [key] })),
      );
      toast.show(t('collection.deleted'));
      onClose();
      onDeleted?.();
    },
    onError: () => toast.show(t('errors.generic'), 'error'),
  });

  return (
    <ConfirmDialog
      open={item !== null}
      title={t('collection.deleteTitle')}
      confirmLabel={t('common.delete')}
      onCancel={onClose}
      onConfirm={() => item && mutation.mutate(item.id)}
      busy={mutation.isPending}
      danger
    >
      {item ? (
        <p data-testid="delete-instance-text">
          {t('collection.deleteText', {
            title: item.title,
            total: formatUah(item.totalUah, i18n.language),
          })}
        </p>
      ) : null}
    </ConfirmDialog>
  );
}
