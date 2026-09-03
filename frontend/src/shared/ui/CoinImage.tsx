import { useState } from 'react';

import styles from './CoinImage.module.css';

interface CoinImageProps {
  /** Absolute or same-origin URL; null whenever the item has no photo. */
  src?: string | null;
  /**
   * Alt text. Pass "" for images that sit next to the coin title: the title
   * already names them, so a repeated description is noise for a screen reader.
   */
  alt: string;
  /** Sizing and shape of the frame — the image and the placeholder fill it. */
  className?: string;
  /** `cover` crops to fill the frame (lists); `contain` shows the whole photo (the card). */
  fit?: 'cover' | 'contain';
}

/**
 * The single visual slot for a coin photo.
 *
 * Many catalog items have no image at all, and part of the stored URLs point at
 * uCoin, which sits behind Cloudflare and usually refuses to serve the file. We
 * do not proxy or retry those (docs/06-media-storage.md — the Ukrainian photos
 * come from the NBU in stage 6); a missing and an unreachable photo simply look
 * the same, and neither shows a broken <img>.
 */
export function CoinImage({ src, alt, className, fit = 'cover' }: CoinImageProps) {
  // Remembering the URL that failed rather than a plain flag gives the reset
  // for free when the item changes, and keeps one failure final: the error
  // handler never rewrites src, so a dead URL is requested once, not in a loop.
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  const frame = className ? `${styles.frame} ${className}` : styles.frame;

  if (!src || src === failedSrc) {
    return (
      <span className={frame} data-testid="coin-placeholder">
        <CoinPlaceholder />
      </span>
    );
  }

  return (
    <span className={frame}>
      <img
        src={src}
        alt={alt}
        loading="lazy"
        decoding="async"
        className={fit === 'contain' ? `${styles.image} ${styles.contain}` : styles.image}
        onError={() => setFailedSrc(src)}
      />
    </span>
  );
}

/** A stylised obverse: rim, milled edge and relief, drawn in the theme colours. */
function CoinPlaceholder() {
  return (
    <svg className={styles.glyph} viewBox="0 0 48 48" aria-hidden="true" focusable="false">
      <circle className={styles.rim} cx="24" cy="24" r="21" />
      <circle className={styles.milling} cx="24" cy="24" r="17.5" />
      <circle className={styles.relief} cx="24" cy="24" r="9" />
      <circle className={styles.relief} cx="24" cy="24" r="3" />
    </svg>
  );
}
