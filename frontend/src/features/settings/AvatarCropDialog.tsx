import { useTranslation } from 'react-i18next';

import { CropDialog } from '@/shared/ui';

import { cropToBlob } from './cropAvatar';

interface AvatarCropDialogProps {
  /** An object URL for the picked file; the caller owns and revokes it. */
  image: string | null;
  busy: boolean;
  onCancel: () => void;
  onSave: (cropped: Blob) => void;
}

/** Pick the visible circle out of a picture before it is uploaded. */
export function AvatarCropDialog({ image, busy, onCancel, onSave }: AvatarCropDialogProps) {
  const { t } = useTranslation();
  return (
    <CropDialog
      image={image}
      title={t('settings.avatarCropTitle')}
      hint={t('settings.avatarCropHint')}
      zoomLabel={t('settings.avatarZoom')}
      invalidMessage={t('settings.avatarInvalid')}
      busy={busy}
      cropShape="round"
      onCancel={onCancel}
      onSave={onSave}
      toBlob={cropToBlob}
    />
  );
}
