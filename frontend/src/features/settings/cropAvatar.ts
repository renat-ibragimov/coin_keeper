import type { Area } from 'react-easy-crop';

/** The largest square we bother encoding: the server stores 256, so pushing a
 *  4000 px crop up the wire only makes the upload slower. */
const MAX_SIDE = 512;
const QUALITY = 0.9;

function encode(canvas: HTMLCanvasElement, type: string): Promise<Blob | null> {
  return new Promise((resolve) => canvas.toBlob(resolve, type, QUALITY));
}

/** Cut the circle the user framed out of the source image.
 *
 * react-easy-crop reports coordinates and nothing else — the pixels are ours
 * to cut. The result is square, not round: the circle is a mask the interface
 * draws, and a transparent corner would only make the file bigger.
 */
export async function cropToBlob(src: string, area: Area): Promise<Blob> {
  const image = await loadImage(src);
  const side = Math.min(MAX_SIDE, Math.round(area.width));
  const canvas = document.createElement('canvas');
  canvas.width = side;
  canvas.height = side;

  const context = canvas.getContext('2d');
  if (!context) throw new Error('canvas is unavailable');
  context.imageSmoothingQuality = 'high';
  context.drawImage(image, area.x, area.y, area.width, area.height, 0, 0, side, side);

  const webp = await encode(canvas, 'image/webp');
  // Older Safari ignores the requested type and hands back a PNG without
  // saying so, which would reach the server mislabelled as WebP.
  if (webp && webp.type === 'image/webp') return webp;

  const jpeg = await encode(canvas, 'image/jpeg');
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
