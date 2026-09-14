import { useTranslation } from 'react-i18next';

import { CropDialog } from '@/shared/ui';

import { cropToBlob } from './cropCoinPhoto';

interface CoinPhotoCropDialogProps {
  /** An object URL for the picked file; the caller owns and revokes it. */
  image: string | null;
  busy: boolean;
  onCancel: () => void;
  onSave: (cropped: Blob) => void;
}

/** A viewfinder circle over the coin photo; the server gets the square behind it. */
export function CoinPhotoCropDialog({ image, busy, onCancel, onSave }: CoinPhotoCropDialogProps) {
  const { t } = useTranslation();
  return (
    <CropDialog
      image={image}
      title={t('collectionPhoto.cropTitle')}
      hint={t('collectionPhoto.cropHint')}
      zoomLabel={t('settings.avatarZoom')}
      invalidMessage={t('collectionPhoto.invalid')}
      busy={busy}
      cropShape="round"
      onCancel={onCancel}
      onSave={onSave}
      toBlob={cropToBlob}
    />
  );
}
