import { describe, expect, it } from 'vitest';

import { isLikelyBlurry, laplacianVariance } from './blurCheck';
import type { RgbaSample } from './blurCheck';

const SIDE = 40;

/** A synthetic round-photo buffer: transparent outside the circle (as
 *  `applyCircleAlpha` would leave it), opaque and filled by `gray(x, y)`
 *  inside — matching what the real pipeline hands to the blur check. */
function buildSample(gray: (x: number, y: number) => number): RgbaSample {
  const data = new Uint8ClampedArray(SIDE * SIDE * 4);
  const radius = SIDE / 2;
  const cx = SIDE / 2;
  const cy = SIDE / 2;
  for (let y = 0; y < SIDE; y++) {
    for (let x = 0; x < SIDE; x++) {
      const i = (y * SIDE + x) * 4;
      const inside = (x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2 <= radius * radius;
      const value = gray(x, y);
      data[i] = value;
      data[i + 1] = value;
      data[i + 2] = value;
      data[i + 3] = inside ? 255 : 0;
    }
  }
  return { width: SIDE, height: SIDE, data };
}

describe('laplacianVariance / isLikelyBlurry', () => {
  it('scores a flat, featureless photo as blurry', () => {
    const flat = buildSample(() => 128);
    expect(laplacianVariance(flat)).toBe(0);
    expect(isLikelyBlurry(flat)).toBe(true);
  });

  it('scores a high-contrast, detailed photo as not blurry', () => {
    const checkerboard = buildSample((x, y) => ((x + y) % 2 === 0 ? 255 : 0));
    expect(laplacianVariance(checkerboard)).toBeGreaterThan(1000);
    expect(isLikelyBlurry(checkerboard)).toBe(false);
  });

  it('ignores the fully transparent corners outside the circle', () => {
    // A noisy corner (which applyCircleAlpha would have made transparent
    // anyway) must not change the verdict for the visible interior.
    const flatWithNoisyCorner = buildSample((x, y) => {
      if (x < 2 && y < 2) return (x + y) % 2 === 0 ? 255 : 0;
      return 128;
    });
    expect(isLikelyBlurry(flatWithNoisyCorner)).toBe(true);
  });

  it('respects a custom threshold', () => {
    const checkerboard = buildSample((x, y) => ((x + y) % 2 === 0 ? 255 : 0));
    const variance = laplacianVariance(checkerboard);
    expect(isLikelyBlurry(checkerboard, variance + 1)).toBe(true);
    expect(isLikelyBlurry(checkerboard, variance - 1)).toBe(false);
  });
});
