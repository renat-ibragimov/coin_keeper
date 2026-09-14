import { useState } from 'react';
import Cropper from 'react-easy-crop';
import type { Area, Point } from 'react-easy-crop';
import { useTranslation } from 'react-i18next';

import { Button, FormError, Modal } from '@/shared/ui';

import { cropToBlob } from './cropAvatar';
import styles from './AvatarCropDialog.module.css';

interface AvatarCropDialogProps {
  /** An object URL for the picked file; the caller owns and revokes it. */
  image: string | null;
  busy: boolean;
  onCancel: () => void;
  onSave: (cropped: Blob) => void;
}

const MIN_ZOOM = 1;
const MAX_ZOOM = 3;

/** Pick the visible circle out of a picture before it is uploaded. */
export function AvatarCropDialog({ image, busy, onCancel, onSave }: AvatarCropDialogProps) {
  const { t } = useTranslation();
  const [crop, setCrop] = useState<Point>({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(MIN_ZOOM);
  const [area, setArea] = useState<Area | null>(null);
  const [failed, setFailed] = useState(false);

  async function save() {
    if (!image || !area) return;
    setFailed(false);
    try {
      onSave(await cropToBlob(image, area));
    } catch {
      // Reading or encoding the picture failed in this browser — nothing was
      // sent, so this is the dialog's problem to report, not the server's.
      setFailed(true);
    }
  }

  return (
    <Modal
      open={image !== null}
      onClose={onCancel}
      title={t('settings.avatarCropTitle')}
      size="sm"
      footer={
        <>
          <Button variant="ghost" onClick={onCancel} disabled={busy}>
            {t('common.cancel')}
          </Button>
          <Button onClick={() => void save()} loading={busy} disabled={area === null}>
            {t('common.save')}
          </Button>
        </>
      }
    >
      {/* Cropper positions itself absolutely, so it needs a sized, relative
          box to fill — without one it collapses to nothing. */}
      <div className={styles.stage}>
        {image ? (
          <Cropper
            image={image}
            crop={crop}
            zoom={zoom}
            aspect={1}
            cropShape="round"
            showGrid={false}
            onCropChange={setCrop}
            onZoomChange={setZoom}
            onCropComplete={(_, pixels) => setArea(pixels)}
          />
        ) : null}
      </div>
      <label className={styles.zoom}>
        <span className={styles.zoomLabel}>{t('settings.avatarZoom')}</span>
        <input
          type="range"
          min={MIN_ZOOM}
          max={MAX_ZOOM}
          step={0.01}
          value={zoom}
          onChange={(event) => setZoom(Number(event.target.value))}
          className={styles.zoomSlider}
        />
      </label>
      <p className={styles.hint}>{t('settings.avatarCropHint')}</p>
      <FormError>{failed ? t('settings.avatarInvalid') : null}</FormError>
    </Modal>
  );
}
