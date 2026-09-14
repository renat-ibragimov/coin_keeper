import { useTranslation } from 'react-i18next';

import { CropDialog } from '@/shared/ui';

import { checkBlur, cropToBlob } from './cropCoinPhoto';

interface CoinPhotoCropDialogProps {
  /** An object URL for the picked file; the caller owns and revokes it. */
  image: string | null;
  busy: boolean;
  onCancel: () => void;
  onSave: (cropped: Blob) => void;
}

const MIN_ZOOM = 1;
const MAX_ZOOM = 5;
const ROTATION_MIN = -15;
const ROTATION_MAX = 15;
const ROTATION_STEP = 1;

/** A viewfinder circle over the coin photo; the server gets a real
 *  transparent-cornered cut of whatever the user framed and straightened. */
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
      minZoom={MIN_ZOOM}
      maxZoom={MAX_ZOOM}
      rotation={{
        min: ROTATION_MIN,
        max: ROTATION_MAX,
        step: ROTATION_STEP,
        label: t('collectionPhoto.rotationLabel'),
        resetLabel: t('collectionPhoto.resetRotation'),
      }}
      blur={{
        check: checkBlur,
        warning: t('collectionPhoto.blurWarning'),
        saveAnywayLabel: t('collectionPhoto.saveAnyway'),
      }}
      onCancel={onCancel}
      onSave={onSave}
      toBlob={cropToBlob}
    />
  );
}
