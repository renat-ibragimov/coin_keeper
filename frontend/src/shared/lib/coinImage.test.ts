import { describe, expect, it } from 'vitest';

import { imageSources } from './coinImage';

const stored = {
  preview: 'p_300.webp',
  medium: 'p_600.webp',
  large: 'p_1200.webp',
  attribution: 'Національний банк України',
};

describe('imageSources', () => {
  it('takes the size the place needs and offers the next one up', () => {
    expect(imageSources(stored, 'list')).toEqual({
      src: 'p_300.webp',
      srcSet: 'p_300.webp 1x, p_600.webp 2x',
    });
    expect(imageSources(stored, 'card')).toEqual({
      src: 'p_600.webp',
      srcSet: 'p_600.webp 1x, p_1200.webp 2x',
    });
    expect(imageSources(stored, 'lightbox')).toEqual({ src: 'p_1200.webp' });
  });

  it('does not announce a second resolution the coin does not have', () => {
    // ua-coins serves 600 px at most, so the API repeats it as the large one.
    const capped = { ...stored, large: 'p_600.webp' };
    expect(imageSources(capped, 'card')).toEqual({ src: 'p_600.webp' });
    expect(imageSources(capped, 'lightbox')).toEqual({ src: 'p_600.webp' });
  });

  it('is empty when there is no photo', () => {
    expect(imageSources(null, 'card')).toEqual({ src: null });
    expect(
      imageSources({ preview: null, medium: null, large: null, attribution: null }, 'list'),
    ).toEqual({ src: null });
  });
});
