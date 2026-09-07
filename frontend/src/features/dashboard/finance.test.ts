import { describe, expect, it } from 'vitest';

import { myCollectionSeries, valueDelta } from './finance';

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

describe('myCollectionSeries', () => {
  it('orders started series by share, closest to completion first, drops untouched ones', () => {
    const result = myCollectionSeries([
      { id: 2, name: 'Half', country: 'Ukraine', count: 10, owned: 5 },
      { id: 3, name: 'Almost', country: 'Ukraine', count: 20, owned: 19 },
      { id: 4, name: 'Empty', country: 'Ukraine', count: 0, owned: 0 },
      { id: 5, name: 'Started', country: 'USA', count: 3, owned: 1 },
      { id: 6, name: 'Untouched', country: 'USA', count: 5, owned: 0 },
    ]);
    expect(result.map((entry) => entry.name)).toEqual(['Almost', 'Half', 'Started']);
    expect(result[0]).toMatchObject({ ratio: 0.95, missing: 1 });
  });

  it('breaks a tie by the number of coins still missing', () => {
    const result = myCollectionSeries([
      { id: 1, name: 'Big', country: 'Ukraine', count: 100, owned: 50 },
      { id: 2, name: 'Small', country: 'Ukraine', count: 2, owned: 1 },
    ]);
    expect(result.map((entry) => entry.name)).toEqual(['Small', 'Big']);
  });

  it('keeps completed series in the list, pushed to the end', () => {
    const result = myCollectionSeries([
      { id: 1, name: 'Done', country: 'Ukraine', count: 4, owned: 4 },
      { id: 2, name: 'Half', country: 'Ukraine', count: 10, owned: 5 },
      { id: 3, name: 'AlsoDone', country: 'USA', count: 2, owned: 2 },
    ]);
    expect(result.map((entry) => entry.name)).toEqual(['Half', 'AlsoDone', 'Done']);
    expect(result[1]).toMatchObject({ ratio: 1, missing: 0 });
  });
});
