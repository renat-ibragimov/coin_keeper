import { describe, expect, it, vi } from 'vitest';

import {
  applyCircleAlpha,
  encodeAlphaBlob,
  formatRotationDegrees,
  rotatedBoundingBox,
} from './rotatedCircleCrop';

describe('rotatedBoundingBox', () => {
  it('is a no-op at 0°', () => {
    expect(rotatedBoundingBox(200, 120, 0)).toEqual({ width: 200, height: 120 });
  });

  it('matches react-easy-crop for a symmetric ±15° tilt', () => {
    const plus = rotatedBoundingBox(200, 120, 15);
    const minus = rotatedBoundingBox(200, 120, -15);
    expect(plus).toEqual(minus);
    expect(plus.width).toBeGreaterThan(200);
    expect(plus.height).toBeGreaterThan(120);
  });

  it('swaps width and height at 90°', () => {
    const { width, height } = rotatedBoundingBox(200, 120, 90);
    expect(width).toBeCloseTo(120);
    expect(height).toBeCloseTo(200);
  });
});

describe('formatRotationDegrees', () => {
  it('formats zero without a sign', () => {
    expect(formatRotationDegrees(0)).toBe('0°');
  });

  it('formats a positive tilt with a plus sign', () => {
    expect(formatRotationDegrees(7)).toBe('+7°');
  });

  it('formats a negative tilt with a real minus sign', () => {
    expect(formatRotationDegrees(-4)).toBe('−4°');
  });

  it('rounds fractional degrees', () => {
    expect(formatRotationDegrees(6.6)).toBe('+7°');
  });
});

describe('applyCircleAlpha', () => {
  function opaqueSquare(side: number): Uint8ClampedArray {
    const data = new Uint8ClampedArray(side * side * 4);
    data.fill(255);
    return data;
  }

  it('makes every corner transparent and leaves the centre opaque', () => {
    const side = 100;
    const data = opaqueSquare(side);
    applyCircleAlpha(data, side, side);

    const alphaAt = (x: number, y: number) => data[(y * side + x) * 4 + 3];
    expect(alphaAt(0, 0)).toBe(0);
    expect(alphaAt(side - 1, 0)).toBe(0);
    expect(alphaAt(0, side - 1)).toBe(0);
    expect(alphaAt(side - 1, side - 1)).toBe(0);
    expect(alphaAt(side / 2, side / 2)).toBe(255);
  });

  it('cuts exactly at the circle boundary — no inner or outer margin', () => {
    const side = 100;
    const data = opaqueSquare(side);
    applyCircleAlpha(data, side, side);

    const alphaAt = (x: number, y: number) => data[(y * side + x) * 4 + 3];
    // Centre of the square is (50, 50); radius is exactly 50.
    // (99, 50): distance ≈ 49.5 from centre — inside the true circle, but a
    // 3% inward shrink (radius 48.5) would wrongly cut it.
    expect(alphaAt(99, 50)).toBe(255);
    // (85, 85): distance ≈ 50.2 from centre — just outside the true circle,
    // but a 3% outward pad (radius 51.5) would wrongly keep it.
    expect(alphaAt(85, 85)).toBe(0);
  });
});

describe('encodeAlphaBlob', () => {
  function canvasWithToBlob(
    respond: (type: string) => Blob | null,
  ): HTMLCanvasElement & { toBlob: ReturnType<typeof vi.fn> } {
    const canvas = document.createElement('canvas') as HTMLCanvasElement & {
      toBlob: ReturnType<typeof vi.fn>;
    };
    canvas.toBlob = vi.fn((callback: BlobCallback, type?: string) => {
      callback(respond(type ?? ''));
    });
    return canvas;
  }

  it('keeps a webp blob the browser actually produced', async () => {
    const canvas = canvasWithToBlob((type) => new Blob(['x'], { type }));
    const blob = await encodeAlphaBlob(canvas, 0.9);
    expect(blob.type).toBe('image/webp');
    expect(canvas.toBlob).toHaveBeenCalledTimes(1);
  });

  it('falls back to PNG when the browser silently ignores the webp request', async () => {
    const requestedTypes: string[] = [];
    const canvas = canvasWithToBlob((type) => {
      requestedTypes.push(type);
      // Simulates a browser (older Safari) handing back something that is
      // not actually WebP without saying so via a rejected/odd MIME type.
      return new Blob(['x'], { type: type === 'image/webp' ? 'image/x-not-webp' : type });
    });
    const blob = await encodeAlphaBlob(canvas, 0.9);
    expect(blob.type).toBe('image/png');
    expect(requestedTypes).toEqual(['image/webp', 'image/png']);
  });

  it('never falls back to JPEG', async () => {
    const canvas = canvasWithToBlob(() => null);
    await expect(encodeAlphaBlob(canvas, 0.9)).rejects.toThrow();
    expect(canvas.toBlob).toHaveBeenCalledTimes(2);
    const requestedTypes = (canvas.toBlob.mock.calls as [BlobCallback, string][]).map(
      ([, type]) => type,
    );
    expect(requestedTypes).not.toContain('image/jpeg');
  });
});
