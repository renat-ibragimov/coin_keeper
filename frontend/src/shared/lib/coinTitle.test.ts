import type { TFunction } from 'i18next';
import { describe, expect, it } from 'vitest';

import { coinTitle, seriesLabel, showsOriginal } from './coinTitle';

const t = ((key: string) => key) as TFunction;

const dolphin = {
  titleOriginal: 'Дельфін',
  titleUk: 'Дельфін',
  titleEn: 'Dolphin',
};

describe('coinTitle', () => {
  it('takes the slot of the requested locale', () => {
    expect(coinTitle(dolphin, 'uk')).toBe('Дельфін');
    expect(coinTitle(dolphin, 'en')).toBe('Dolphin');
    expect(coinTitle(dolphin, 'en-GB')).toBe('Dolphin');
  });

  it('falls back to the original, and only to the original', () => {
    const soviet = { titleOriginal: 'Рубль', titleUk: null, titleEn: null };
    expect(coinTitle(soviet, 'uk')).toBe('Рубль');
    expect(coinTitle(soviet, 'en')).toBe('Рубль');
    expect(coinTitle({ ...soviet, titleUk: '  ' }, 'uk')).toBe('Рубль');
  });

  it('trims surrounding whitespace', () => {
    expect(coinTitle({ titleOriginal: 'Owl', titleUk: ' Сова ', titleEn: null }, 'uk')).toBe(
      'Сова',
    );
  });
});

describe('showsOriginal', () => {
  it('is true only when the reader is looking at a translation', () => {
    expect(showsOriginal(dolphin, 'en')).toBe(true);
    expect(showsOriginal(dolphin, 'uk')).toBe(false);
    expect(showsOriginal({ titleOriginal: 'Рубль', titleUk: null, titleEn: null }, 'en')).toBe(
      false,
    );
  });
});

describe('seriesLabel', () => {
  it('is the series name when the coin has one', () => {
    expect(seriesLabel({ seriesName: 'Софіївка', collectionGroup: 'commemorative' }, t)).toBe(
      'Софіївка',
    );
  });

  it('falls back to a circulation stand-in when a circulation coin has no series', () => {
    expect(seriesLabel({ seriesName: null, collectionGroup: 'circulation' }, t)).toBe(
      'catalog.circulationSeries',
    );
  });

  it('is null for any other group without a series', () => {
    expect(seriesLabel({ seriesName: null, collectionGroup: 'commemorative' }, t)).toBeNull();
    expect(seriesLabel({ seriesName: null, collectionGroup: 'collector' }, t)).toBeNull();
    expect(seriesLabel({ seriesName: null, collectionGroup: 'other' }, t)).toBeNull();
  });
});
