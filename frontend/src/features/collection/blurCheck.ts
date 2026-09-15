/**
 * A soft UX heuristic, not a quality guarantee: variance of a Laplacian
 * response over the photo's trusted interior. Real coin photos were not used
 * to tune it — only the synthetic sharp/flat samples in blurCheck.test.ts —
 * so treat it as "probably too flat to be in focus", not proof either way.
 */
export const BLUR_VARIANCE_THRESHOLD = 120;

const OPAQUE_ALPHA_MIN = 250;
/** Keeps the mask's own hard edge out of the analysis — a crisp circle
 *  boundary is high-frequency too, and would read as false sharpness. */
const EDGE_MARGIN_FRACTION = 0.06;

export interface RgbaSample {
  width: number;
  height: number;
  data: ArrayLike<number>;
}

function grayscaleInterior(sample: RgbaSample): { gray: Float64Array; included: Uint8Array } {
  const { width, height, data } = sample;
  const gray = new Float64Array(width * height);
  const included = new Uint8Array(width * height);
  const radius = (Math.min(width, height) / 2) * (1 - EDGE_MARGIN_FRACTION);
  const cx = width / 2;
  const cy = height / 2;

  for (let y = 0; y < height; y++) {
    const dy = y + 0.5 - cy;
    for (let x = 0; x < width; x++) {
      const i = y * width + x;
      const offset = i * 4;
      const dx = x + 0.5 - cx;
      const inside = dx * dx + dy * dy <= radius * radius;
      const opaque = (data[offset + 3] ?? 0) >= OPAQUE_ALPHA_MIN;
      included[i] = inside && opaque ? 1 : 0;
      gray[i] =
        0.299 * (data[offset] ?? 0) +
        0.587 * (data[offset + 1] ?? 0) +
        0.114 * (data[offset + 2] ?? 0);
    }
  }
  return { gray, included };
}

/**
 * Variance of a Laplacian response — the classic "variance of Laplacian"
 * sharpness metric, reimplemented by hand instead of pulled in from OpenCV.
 * A flat, low-frequency photo scores low; a photo with real detail scores
 * high. Transparent pixels outside the circle, and a thin ring at its edge,
 * are excluded from every pixel they touch as a neighbour.
 */
export function laplacianVariance(sample: RgbaSample): number {
  const { width, height } = sample;
  const { gray, included } = grayscaleInterior(sample);
  const responses: number[] = [];

  for (let y = 1; y < height - 1; y++) {
    for (let x = 1; x < width - 1; x++) {
      const i = y * width + x;
      const up = i - width;
      const down = i + width;
      const left = i - 1;
      const right = i + 1;
      if (!included[i] || !included[up] || !included[down] || !included[left] || !included[right]) {
        continue;
      }
      responses.push(
        (gray[up] ?? 0) +
          (gray[down] ?? 0) +
          (gray[left] ?? 0) +
          (gray[right] ?? 0) -
          4 * (gray[i] ?? 0),
      );
    }
  }

  if (responses.length === 0) return 0;
  const mean = responses.reduce((sum, value) => sum + value, 0) / responses.length;
  return responses.reduce((sum, value) => sum + (value - mean) ** 2, 0) / responses.length;
}

export function isLikelyBlurry(sample: RgbaSample, threshold = BLUR_VARIANCE_THRESHOLD): boolean {
  return laplacianVariance(sample) < threshold;
}
