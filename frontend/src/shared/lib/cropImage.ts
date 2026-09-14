import type { Area } from 'react-easy-crop';

function encode(canvas: HTMLCanvasElement, type: string, quality: number): Promise<Blob | null> {
  return new Promise((resolve) => canvas.toBlob(resolve, type, quality));
}

/** Cut the square the user framed out of the source image.
 *
 * react-easy-crop reports coordinates and nothing else — the pixels are ours
 * to cut. The result is square, not round: a circular crop shape is a mask
 * the interface draws over a square stage, and a transparent corner would
 * only make the file bigger for no one to see.
 */
export async function cropToSquareBlob(
  src: string,
  area: Area,
  { maxSide, quality }: { maxSide: number; quality: number },
): Promise<Blob> {
  const image = await loadImage(src);
  const side = Math.min(maxSide, Math.round(area.width));
  const canvas = document.createElement('canvas');
  canvas.width = side;
  canvas.height = side;

  const context = canvas.getContext('2d');
  if (!context) throw new Error('canvas is unavailable');
  context.imageSmoothingQuality = 'high';
  context.drawImage(image, area.x, area.y, area.width, area.height, 0, 0, side, side);

  const webp = await encode(canvas, 'image/webp', quality);
  // Older Safari ignores the requested type and hands back a PNG without
  // saying so, which would reach the server mislabelled as WebP.
  if (webp && webp.type === 'image/webp') return webp;

  const jpeg = await encode(canvas, 'image/jpeg', quality);
  if (!jpeg) throw new Error('the picture could not be encoded');
  return jpeg;
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.addEventListener('load', () => resolve(image));
    image.addEventListener('error', () => reject(new Error('the picture could not be read')));
    image.src = src;
  });
}
