import type { components } from '@/shared/api/generated/openapi';

export type CoinImageOut = components['schemas']['CoinImageOut'];

/** What an <img> needs: the size for this place, and the next one up for a dense screen. */
export interface ImageSources {
  src: string | null;
  srcSet?: string;
}

/**
 * Which stored size belongs where (docs/06-media-storage.md):
 * a listing shows the preview, a card the medium, the lightbox the large.
 *
 * The srcSet offers the next size up at 2x, so a retina screen gets the
 * sharper file and an ordinary one does not pay for it. A coin stored at
 * 600 px has no larger form — the API repeats the largest it has, and the
 * duplicate is dropped here rather than announced as a second resolution.
 */
export function imageSources(
  image: CoinImageOut | null | undefined,
  place: 'list' | 'card' | 'lightbox',
): ImageSources {
  if (!image) return { src: null };
  if (place === 'lightbox') return { src: image.large ?? image.medium ?? image.preview };
  const [one, two] = place === 'list' ? [image.preview, image.medium] : [image.medium, image.large];
  const src = one ?? two ?? image.preview;
  if (!src) return { src: null };
  const denser = two && two !== src ? two : null;
  return denser ? { src, srcSet: `${src} 1x, ${denser} 2x` } : { src };
}
