import type { Area } from 'react-easy-crop';

import { loadImage } from '@/shared/lib/cropImage';
import { cropRotatedRoundBlob } from '@/shared/lib/rotatedCircleCrop';

import { isLikelyBlurry } from './blurCheck';

/** The server stores up to 1200 px; a bit of headroom so its own resize is
 *  never asked to sharpen a source that arrived smaller than the target. */
const MAX_SIDE = 1600;
const QUALITY = 0.95;
/** Small enough to analyse without noticeable delay, large enough that the
 *  Laplacian response still means something (docs/06-media-storage.md). */
const BLUR_CHECK_SIDE = 256;

export function cropToBlob(src: string, area: Area, rotation: number): Promise<Blob> {
  return cropRotatedRoundBlob(src, area, { rotation, maxSide: MAX_SIDE, quality: QUALITY });
}

/** Decodes the already-cropped Blob back into pixels for the blur heuristic —
 *  cheap at BLUR_CHECK_SIDE, and it never leaves the browser. */
export async function checkBlur(blob: Blob): Promise<boolean> {
  const url = URL.createObjectURL(blob);
  try {
    const image = await loadImage(url);
    const canvas = document.createElement('canvas');
    canvas.width = BLUR_CHECK_SIDE;
    canvas.height = BLUR_CHECK_SIDE;
    const context = canvas.getContext('2d');
    if (!context) return false;
    context.drawImage(image, 0, 0, BLUR_CHECK_SIDE, BLUR_CHECK_SIDE);
    const { data } = context.getImageData(0, 0, BLUR_CHECK_SIDE, BLUR_CHECK_SIDE);
    return isLikelyBlurry({ width: BLUR_CHECK_SIDE, height: BLUR_CHECK_SIDE, data });
  } finally {
    URL.revokeObjectURL(url);
  }
}
