import type { Area } from 'react-easy-crop';

import { cropToSquareBlob } from '@/shared/lib/cropImage';

/** The largest square we bother encoding: the server stores 256, so pushing a
 *  4000 px crop up the wire only makes the upload slower. */
const MAX_SIDE = 512;
const QUALITY = 0.9;

export function cropToBlob(src: string, area: Area): Promise<Blob> {
  return cropToSquareBlob(src, area, { maxSide: MAX_SIDE, quality: QUALITY });
}
