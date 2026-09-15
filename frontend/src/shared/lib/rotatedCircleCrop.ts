import type { Area } from 'react-easy-crop';

import { encode, loadImage } from './cropImage';

/**
 * Bounding box of a `width x height` rectangle rotated by `rotationDegrees`.
 * Mirrors react-easy-crop's own `rotateSize` — `croppedAreaPixels` is
 * expressed in this same rotated coordinate space, so any canvas built to
 * hold the rotated source must use this exact box to line up with it.
 */
export function rotatedBoundingBox(
  width: number,
  height: number,
  rotationDegrees: number,
): { width: number; height: number } {
  const radians = (rotationDegrees * Math.PI) / 180;
  return {
    width: Math.abs(Math.cos(radians) * width) + Math.abs(Math.sin(radians) * height),
    height: Math.abs(Math.sin(radians) * width) + Math.abs(Math.cos(radians) * height),
  };
}

/** `0°`, `+7°`, `−4°` — a proper minus sign, not a hyphen. */
export function formatRotationDegrees(value: number): string {
  const rounded = Math.round(value);
  if (rounded === 0) return '0°';
  return rounded > 0 ? `+${rounded}°` : `−${Math.abs(rounded)}°`;
}

/**
 * Zero the alpha of every pixel whose centre falls outside the circle
 * inscribed in `width x height` — no inner or outer margin, so the file
 * matches the crop circle exactly. Mutates `data` in place.
 */
export function applyCircleAlpha(data: Uint8ClampedArray, width: number, height: number): void {
  const radius = Math.min(width, height) / 2;
  const cx = width / 2;
  const cy = height / 2;
  for (let y = 0; y < height; y++) {
    const dy = y + 0.5 - cy;
    for (let x = 0; x < width; x++) {
      const dx = x + 0.5 - cx;
      if (dx * dx + dy * dy > radius * radius) {
        data[(y * width + x) * 4 + 3] = 0;
      }
    }
  }
}

/** Draw `image`, rotated in place around its own centre, onto a canvas sized
 *  to `rotatedBoundingBox` — the same coordinate space `croppedAreaPixels`
 *  already assumes. */
function drawRotatedSource(image: HTMLImageElement, rotationDegrees: number): HTMLCanvasElement {
  const { width, height } = rotatedBoundingBox(
    image.naturalWidth,
    image.naturalHeight,
    rotationDegrees,
  );
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(width);
  canvas.height = Math.round(height);
  const context = canvas.getContext('2d');
  if (!context) throw new Error('canvas is unavailable');
  context.translate(canvas.width / 2, canvas.height / 2);
  context.rotate((rotationDegrees * Math.PI) / 180);
  context.translate(-image.naturalWidth / 2, -image.naturalHeight / 2);
  context.drawImage(image, 0, 0);
  return canvas;
}

function extractArea(source: HTMLCanvasElement, area: Area): HTMLCanvasElement {
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(area.width);
  canvas.height = Math.round(area.height);
  const context = canvas.getContext('2d');
  if (!context) throw new Error('canvas is unavailable');
  context.drawImage(
    source,
    area.x,
    area.y,
    area.width,
    area.height,
    0,
    0,
    canvas.width,
    canvas.height,
  );
  return canvas;
}

function resizeSquare(source: HTMLCanvasElement, side: number): HTMLCanvasElement {
  if (source.width === side && source.height === side) return source;
  const canvas = document.createElement('canvas');
  canvas.width = side;
  canvas.height = side;
  const context = canvas.getContext('2d');
  if (!context) throw new Error('canvas is unavailable');
  context.imageSmoothingQuality = 'high';
  context.drawImage(source, 0, 0, source.width, source.height, 0, 0, side, side);
  return canvas;
}

function maskToCircle(canvas: HTMLCanvasElement): void {
  const context = canvas.getContext('2d');
  if (!context) throw new Error('canvas is unavailable');
  const image = context.getImageData(0, 0, canvas.width, canvas.height);
  applyCircleAlpha(image.data, canvas.width, canvas.height);
  context.putImageData(image, 0, 0);
}

export async function encodeAlphaBlob(canvas: HTMLCanvasElement, quality: number): Promise<Blob> {
  const webp = await encode(canvas, 'image/webp', quality);
  // Some browsers ignore the requested type and hand back something else
  // without saying so; a round photo needs real alpha, so JPEG is never an
  // acceptable fallback here — PNG is the only alternative.
  if (webp && webp.type === 'image/webp') return webp;

  const png = await encode(canvas, 'image/png', 1);
  if (!png) throw new Error('the picture could not be encoded');
  return png;
}

/**
 * Cut the circle the user framed out of a rotated picture, with real
 * transparency outside it. Follows react-easy-crop's own recipe for
 * combining `rotation` with `croppedAreaPixels`: render the whole source
 * rotated around its centre onto a bounding-box canvas first, then crop —
 * doing it any other order would put the crop rectangle in the wrong
 * coordinate space.
 */
export async function cropRotatedRoundBlob(
  src: string,
  area: Area,
  { rotation, maxSide, quality }: { rotation: number; maxSide: number; quality: number },
): Promise<Blob> {
  const image = await loadImage(src);
  const rotated = drawRotatedSource(image, rotation);
  const cropped = extractArea(rotated, area);
  const side = Math.min(maxSide, Math.round(area.width));
  const resized = resizeSquare(cropped, side);
  maskToCircle(resized);
  return encodeAlphaBlob(resized, quality);
}
