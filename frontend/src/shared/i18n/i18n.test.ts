import { describe, expect, it } from 'vitest';

import en from './en.json';
import i18n from './index';
import uk from './uk.json';

function flattenKeys(value: object, prefix = ''): string[] {
  return Object.entries(value).flatMap(([key, child]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    return typeof child === 'object' && child !== null ? flattenKeys(child, path) : [path];
  });
}

describe('i18n', () => {
  it('defaults to Ukrainian', () => {
    expect(i18n.language).toBe('uk');
    expect(i18n.t('nav.catalog')).toBe('Каталог');
  });

  it('keeps uk and en key sets identical', () => {
    expect(flattenKeys(uk).sort()).toEqual(flattenKeys(en).sort());
  });

  it('switches to English at runtime', async () => {
    await i18n.changeLanguage('en');
    expect(i18n.t('nav.missing')).toBe('Missing');
    await i18n.changeLanguage('uk');
    expect(i18n.t('nav.missing')).toBe('Не вистачає');
  });
});
