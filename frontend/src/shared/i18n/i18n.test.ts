import { describe, expect, it } from 'vitest';

import en from './en.json';
import i18n from './index';
import uk from './uk.json';

/** Plural forms differ per language (uk has _few/_many); compare the base keys. */
function flattenKeys(value: object, prefix = ''): string[] {
  const keys = Object.entries(value).flatMap(([key, child]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    return typeof child === 'object' && child !== null
      ? flattenKeys(child, path)
      : [path.replace(/_(zero|one|two|few|many|other)$/, '')];
  });
  return [...new Set(keys)];
}

describe('i18n', () => {
  it('defaults to Ukrainian', () => {
    expect(i18n.language).toBe('uk');
    expect(i18n.t('nav.catalog')).toBe('Каталог');
  });

  it('keeps uk and en key sets identical', () => {
    expect(flattenKeys(uk).sort()).toEqual(flattenKeys(en).sort());
  });

  it('picks Ukrainian plural forms by count', () => {
    expect(i18n.t('card.pieces', { count: 1 })).toBe('1 екземпляр');
    expect(i18n.t('card.pieces', { count: 3 })).toBe('3 екземпляри');
    expect(i18n.t('card.pieces', { count: 11 })).toBe('11 екземплярів');
  });

  it('switches to English at runtime', async () => {
    await i18n.changeLanguage('en');
    expect(i18n.t('nav.missing')).toBe('Missing');
    await i18n.changeLanguage('uk');
    expect(i18n.t('nav.missing')).toBe('Не вистачає');
  });
});
