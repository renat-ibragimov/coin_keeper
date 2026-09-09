import { describe, expect, it } from 'vitest';

import { coinMaterial, shortMaterial } from './coinMaterial';

describe('coinMaterial', () => {
  it('prefers the dictionary name over the free text', () => {
    expect(coinMaterial({ composition: { name: 'Нейзильбер' }, material: 'nickel_silver' })).toBe(
      'Нейзильбер',
    );
  });

  it('falls back to the free text, and to nothing at all', () => {
    expect(coinMaterial({ composition: null, material: 'срібло' })).toBe('срібло');
    expect(coinMaterial({ composition: null, material: '  ' })).toBeNull();
    expect(coinMaterial({ composition: null, material: null })).toBeNull();
  });
});

describe('shortMaterial', () => {
  it('leaves a material that already fits', () => {
    expect(shortMaterial('Нейзильбер')).toBe('Нейзильбер');
    expect(shortMaterial('Срібло 925')).toBe('Срібло 925');
  });

  it('keeps two words of a longer one', () => {
    expect(shortMaterial('Срібло 925 із золотим покриттям')).toBe('Срібло 925…');
  });

  it('drops a trailing short word rather than ending on a preposition', () => {
    expect(shortMaterial('Сталь із латунним покриттям')).toBe('Сталь…');
    expect(shortMaterial('Мідь із марганцево-латунним покриттям')).toBe('Мідь…');
  });
});
