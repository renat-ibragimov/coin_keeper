import { RotateCcw } from 'lucide-react';
import { useState } from 'react';
import Cropper from 'react-easy-crop';
import type { Area, Point } from 'react-easy-crop';
import { useTranslation } from 'react-i18next';

import { formatRotationDegrees } from '@/shared/lib/rotatedCircleCrop';

import { Button } from './Button';
import styles from './CropDialog.module.css';
import { FormError } from './FormLayout';
import { Modal } from './Modal';

interface RotationConfig {
  min: number;
  max: number;
  step: number;
  label: string;
  resetLabel: string;
}

interface BlurConfig {
  /** Runs on the already-produced Blob; the dialog does not build it twice. */
  check: (blob: Blob) => Promise<boolean>;
  warning: string;
  saveAnywayLabel: string;
}

export interface CropDialogProps {
  /** An object URL for the picked file; the caller owns and revokes it. */
  image: string | null;
  title: string;
  hint: string;
  zoomLabel: string;
  invalidMessage: string;
  busy: boolean;
  cropShape?: 'round' | 'rect';
  minZoom?: number;
  maxZoom?: number;
  /** Omitted entirely, the dialog has no rotation control — the avatar crop. */
  rotation?: RotationConfig;
  /** Omitted entirely, saving skips the sharpness check — the avatar crop. */
  blur?: BlurConfig;
  onCancel: () => void;
  onSave: (cropped: Blob) => void;
  toBlob: (src: string, area: Area, rotation: number) => Promise<Blob>;
}

const DEFAULT_MIN_ZOOM = 1;
const DEFAULT_MAX_ZOOM = 3;

/**
 * Frame a square out of a picture before it goes anywhere near the server.
 *
 * Shared by the avatar (a round mask over the square) and coin photo (an
 * actual round, rotation-aware cut) flows: both pick one area out of one
 * image, and `rotation`/`blur` stay undefined for the avatar so it keeps its
 * original behaviour untouched.
 */
export function CropDialog({
  image,
  title,
  hint,
  zoomLabel,
  invalidMessage,
  busy,
  cropShape = 'round',
  minZoom = DEFAULT_MIN_ZOOM,
  maxZoom = DEFAULT_MAX_ZOOM,
  rotation,
  blur,
  onCancel,
  onSave,
  toBlob,
}: CropDialogProps) {
  const { t } = useTranslation();
  const [crop, setCrop] = useState<Point>({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(minZoom);
  const [rotationDeg, setRotationDeg] = useState(0);
  const [area, setArea] = useState<Area | null>(null);
  const [failed, setFailed] = useState(false);
  const [blurWarning, setBlurWarning] = useState<Blob | null>(null);
  // Encoding and the blur check both run before `busy` (the caller's upload
  // state) ever turns on — without this, a second click during that window
  // would start a second encode.
  const [encoding, setEncoding] = useState(false);

  async function save() {
    if (!image || !area) return;
    setFailed(false);
    setEncoding(true);
    try {
      const blob = await toBlob(image, area, rotationDeg);
      const blurry = blur ? await blur.check(blob).catch(() => false) : false;
      if (blurry) {
        setBlurWarning(blob);
        return;
      }
      onSave(blob);
    } catch {
      // Reading or encoding the picture failed in this browser — nothing was
      // sent, so this is the dialog's problem to report, not the server's.
      setFailed(true);
    } finally {
      setEncoding(false);
    }
  }

  function saveAnyway() {
    if (!blurWarning) return;
    onSave(blurWarning);
    setBlurWarning(null);
  }

  return (
    <Modal
      open={image !== null}
      onClose={onCancel}
      title={title}
      size="sm"
      footer={
        blur && blurWarning ? (
          <>
            <Button variant="ghost" onClick={() => setBlurWarning(null)} disabled={busy}>
              {t('common.cancel')}
            </Button>
            <Button onClick={saveAnyway} loading={busy}>
              {blur.saveAnywayLabel}
            </Button>
          </>
        ) : (
          <>
            <Button variant="ghost" onClick={onCancel} disabled={busy || encoding}>
              {t('common.cancel')}
            </Button>
            <Button onClick={() => void save()} loading={busy || encoding} disabled={area === null}>
              {t('common.save')}
            </Button>
          </>
        )
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
            rotation={rotationDeg}
            minZoom={minZoom}
            maxZoom={maxZoom}
            aspect={1}
            cropShape={cropShape}
            showGrid={false}
            onCropChange={setCrop}
            onZoomChange={setZoom}
            onRotationChange={setRotationDeg}
            onCropComplete={(_, pixels) => setArea(pixels)}
          />
        ) : null}
      </div>
      <label className={styles.zoom}>
        <span className={styles.zoomLabel}>{zoomLabel}</span>
        <input
          type="range"
          min={minZoom}
          max={maxZoom}
          step={0.01}
          value={zoom}
          onChange={(event) => setZoom(Number(event.target.value))}
          className={styles.zoomSlider}
        />
      </label>
      {rotation ? (
        <div className={styles.rotation}>
          <label className={styles.rotationLabel} htmlFor="crop-dialog-rotation">
            {rotation.label}
          </label>
          <input
            id="crop-dialog-rotation"
            type="range"
            min={rotation.min}
            max={rotation.max}
            step={rotation.step}
            value={rotationDeg}
            onChange={(event) => setRotationDeg(Number(event.target.value))}
            className={styles.rotationSlider}
          />
          <span className={styles.rotationValue}>{formatRotationDegrees(rotationDeg)}</span>
          <button
            type="button"
            className={styles.rotationReset}
            aria-label={rotation.resetLabel}
            disabled={rotationDeg === 0}
            onClick={() => setRotationDeg(0)}
          >
            <RotateCcw size={16} aria-hidden="true" />
          </button>
        </div>
      ) : null}
      <p className={styles.hint}>{hint}</p>
      {blur && blurWarning ? (
        <div className={styles.warning} role="alert">
          {blur.warning}
        </div>
      ) : null}
      <FormError>{failed ? invalidMessage : null}</FormError>
    </Modal>
  );
}
