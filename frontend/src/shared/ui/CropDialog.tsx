import { useState } from 'react';
import Cropper from 'react-easy-crop';
import type { Area, Point } from 'react-easy-crop';
import { useTranslation } from 'react-i18next';

import { Button } from './Button';
import styles from './CropDialog.module.css';
import { FormError } from './FormLayout';
import { Modal } from './Modal';

interface CropDialogProps {
  /** An object URL for the picked file; the caller owns and revokes it. */
  image: string | null;
  title: string;
  hint: string;
  zoomLabel: string;
  invalidMessage: string;
  busy: boolean;
  cropShape?: 'round' | 'rect';
  onCancel: () => void;
  onSave: (cropped: Blob) => void;
  toBlob: (src: string, area: Area) => Promise<Blob>;
}

const MIN_ZOOM = 1;
const MAX_ZOOM = 3;

/**
 * Frame a square out of a picture before it goes anywhere near the server.
 *
 * Shared by the avatar (a round mask over the square) and coin photo (same
 * mask) crop flows: both pick one area out of one image and hand back one
 * square blob — only the copy and the eventual encoding target differ, which
 * `toBlob` and the caller's own strings carry.
 */
export function CropDialog({
  image,
  title,
  hint,
  zoomLabel,
  invalidMessage,
  busy,
  cropShape = 'round',
  onCancel,
  onSave,
  toBlob,
}: CropDialogProps) {
  const { t } = useTranslation();
  const [crop, setCrop] = useState<Point>({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(MIN_ZOOM);
  const [area, setArea] = useState<Area | null>(null);
  const [failed, setFailed] = useState(false);

  async function save() {
    if (!image || !area) return;
    setFailed(false);
    try {
      onSave(await toBlob(image, area));
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
      title={title}
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
            cropShape={cropShape}
            showGrid={false}
            onCropChange={setCrop}
            onZoomChange={setZoom}
            onCropComplete={(_, pixels) => setArea(pixels)}
          />
        ) : null}
      </div>
      <label className={styles.zoom}>
        <span className={styles.zoomLabel}>{zoomLabel}</span>
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
      <p className={styles.hint}>{hint}</p>
      <FormError>{failed ? invalidMessage : null}</FormError>
    </Modal>
  );
}
