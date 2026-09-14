import type { Area } from 'react-easy-crop';

import { cropToSquareBlob } from '@/shared/lib/cropImage';

/** The server stores up to 1200 px; a bit of headroom so its own resize is
 *  never asked to sharpen a source that arrived smaller than the target. */
const MAX_SIDE = 1600;
const QUALITY = 0.95;

export function cropToBlob(src: string, area: Area): Promise<Blob> {
  return cropToSquareBlob(src, area, { maxSide: MAX_SIDE, quality: QUALITY });
}
