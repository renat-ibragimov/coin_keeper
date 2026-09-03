import { describe, expect, it } from 'vitest';

import { coinTitle } from './coinTitle';

describe('coinTitle', () => {
  it('prefers the Ukrainian title', () => {
    expect(
      coinTitle({
        titleUk: 'Дельфін',
        titleOriginal: 'Dolphin',
        titleEn: 'Dolphin',
        titleRu: 'Дельфин',
      }),
    ).toBe('Дельфін');
  });

  it('falls back to the original before English and Russian', () => {
    expect(
      coinTitle({ titleUk: null, titleOriginal: 'Delfín', titleEn: 'Dolphin', titleRu: 'Дельфин' }),
    ).toBe('Delfín');
    expect(coinTitle({ titleUk: '', titleOriginal: '  ', titleEn: 'Dolphin', titleRu: null })).toBe(
      'Dolphin',
    );
    expect(coinTitle({ titleUk: null, titleOriginal: '', titleEn: null, titleRu: 'Дельфин' })).toBe(
      'Дельфин',
    );
  });

  it('trims surrounding whitespace', () => {
    expect(
      coinTitle({ titleUk: ' Сова ', titleOriginal: 'Owl', titleEn: null, titleRu: null }),
    ).toBe('Сова');
  });
});
