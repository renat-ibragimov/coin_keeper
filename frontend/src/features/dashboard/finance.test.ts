import { describe, expect, it } from 'vitest';

import { nearestToCompletion, valueDelta } from './finance';

describe('valueDelta', () => {
  it('reports the gain against the spend', () => {
    const delta = valueDelta('42765.66', '50000.00');
    expect(delta.diffUah).toBe(7234.34);
    expect(delta.percent).toBeCloseTo(16.92, 2);
  });

  it('reports a loss with a negative sign', () => {
    const delta = valueDelta('1000.00', '750.00');
    expect(delta.diffUah).toBe(-250);
    expect(delta.percent).toBe(-25);
  });

  it('has no percentage when nothing was spent', () => {
    expect(valueDelta('0.00', '120.00')).toEqual({ diffUah: 120, percent: null });
  });

  it('survives malformed input without NaN', () => {
    expect(valueDelta('abc', '1')).toEqual({ diffUah: 0, percent: null });
  });
});

describe('nearestToCompletion', () => {
  it('orders unfinished series by share, closest first, and drops complete ones', () => {
    const result = nearestToCompletion([
      { name: 'Done', country: 'Ukraine', count: 4, owned: 4 },
      { name: 'Half', country: 'Ukraine', count: 10, owned: 5 },
      { name: 'Almost', country: 'Ukraine', count: 20, owned: 19 },
      { name: 'Empty', country: 'Ukraine', count: 0, owned: 0 },
      { name: 'Started', country: 'USA', count: 3, owned: 1 },
    ]);
    expect(result.map((entry) => entry.name)).toEqual(['Almost', 'Half', 'Started']);
    expect(result[0]).toMatchObject({ ratio: 0.95, missing: 1 });
  });

  it('breaks a tie by the number of coins still missing', () => {
    const result = nearestToCompletion([
      { name: 'Big', country: 'Ukraine', count: 100, owned: 50 },
      { name: 'Small', country: 'Ukraine', count: 2, owned: 1 },
    ]);
    expect(result.map((entry) => entry.name)).toEqual(['Small', 'Big']);
  });
});
