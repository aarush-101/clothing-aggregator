import { describe, expect, it } from 'vitest';

import {
  applyFilters,
  buildFacets,
  countActiveFilters,
  emptyFilters,
  sortGroups,
  toggleValue,
  type FilterState,
} from '@/lib/filters';

import { makeGroup, makeProduct } from './fixtures';

function withFilters(overrides: Partial<FilterState>): FilterState {
  return { ...emptyFilters, ...overrides };
}

const shirt = makeGroup(
  { group_id: 'shirt' },
  { product_id: 'shirt', brand: 'Kessler', colours: ['black'], materials: ['linen'] },
);

const trouser = makeGroup(
  { group_id: 'trouser', lowest_total_price: 189 },
  {
    product_id: 'trouser',
    title: 'Verity Supply Wide Trouser',
    brand: 'Verity Supply',
    colours: ['charcoal'],
    materials: ['wool'],
    available_sizes: ['32', '34'],
    price: 189,
    total_price: 189,
    original_price: null,
    discount_percent: null,
    retailer: 'meridian',
    retailer_name: 'Meridian Menswear',
    match_score: 0.6,
  },
);

describe('buildFacets', () => {
  const facets = buildFacets([shirt, trouser]);

  it('collects brands, retailers, colours, sizes and materials', () => {
    expect(facets.brands.map((f) => f.value)).toEqual(
      expect.arrayContaining(['kessler', 'verity supply']),
    );
    expect(facets.retailers.map((f) => f.value)).toEqual(
      expect.arrayContaining(['northbound', 'meridian']),
    );
    expect(facets.colours.map((f) => f.value)).toEqual(
      expect.arrayContaining(['black', 'charcoal']),
    );
    expect(facets.materials.map((f) => f.value)).toEqual(
      expect.arrayContaining(['linen', 'wool']),
    );
  });

  it('orders alpha sizes naturally rather than alphabetically', () => {
    const sizes = buildFacets([shirt]).sizes.map((f) => f.value);
    expect(sizes).toEqual(['s', 'm', 'l']);
  });

  it('orders numeric sizes numerically', () => {
    const sizes = buildFacets([
      makeGroup({ group_id: 'a' }, { available_sizes: ['34', '30', '32'] }),
    ]).sizes.map((f) => f.value);
    expect(sizes).toEqual(['30', '32', '34']);
  });

  it('reports the price range across all offers', () => {
    expect(facets.priceMin).toBe(119);
    expect(facets.priceMax).toBe(189);
  });

  it('flags whether discounts and out-of-stock items exist', () => {
    expect(facets.hasDiscounts).toBe(true);
    expect(facets.hasOutOfStock).toBe(false);
  });

  it('counts a garment once, not once per offer', () => {
    const twoOffers = makeGroup({
      group_id: 'multi',
      offers: [makeProduct({ product_id: 'a' }), makeProduct({ product_id: 'b' })],
      offer_count: 2,
    });
    const brand = buildFacets([twoOffers]).brands.find((f) => f.value === 'kessler');
    expect(brand?.count).toBe(1);
  });

  it('handles an empty result set', () => {
    const empty = buildFacets([]);
    expect(empty.brands).toEqual([]);
    expect(empty.priceMin).toBe(0);
  });
});

describe('applyFilters', () => {
  const groups = [shirt, trouser];

  it('returns everything when nothing is selected', () => {
    expect(applyFilters(groups, emptyFilters)).toHaveLength(2);
  });

  it('filters by brand', () => {
    const result = applyFilters(groups, withFilters({ brands: ['kessler'] }));
    expect(result.map((g) => g.group_id)).toEqual(['shirt']);
  });

  it('filters by colour', () => {
    expect(applyFilters(groups, withFilters({ colours: ['charcoal'] }))).toHaveLength(1);
  });

  it('filters by material', () => {
    expect(applyFilters(groups, withFilters({ materials: ['linen'] }))).toHaveLength(1);
  });

  it('filters by size', () => {
    const result = applyFilters(groups, withFilters({ sizes: ['m'] }));
    expect(result.map((g) => g.group_id)).toEqual(['shirt']);
  });

  it('filters by price range', () => {
    expect(applyFilters(groups, withFilters({ priceRange: [0, 150] }))).toHaveLength(1);
  });

  it('filters out-of-stock items when asked', () => {
    const outOfStock = makeGroup({ group_id: 'oos' }, { in_stock: false, product_id: 'oos' });
    const result = applyFilters([shirt, outOfStock], withFilters({ inStockOnly: true }));
    expect(result.map((g) => g.group_id)).toEqual(['shirt']);
  });

  it('filters to reduced items when asked', () => {
    const result = applyFilters(groups, withFilters({ onSaleOnly: true }));
    expect(result.map((g) => g.group_id)).toEqual(['shirt']);
  });

  it('combines filters with AND', () => {
    expect(
      applyFilters(groups, withFilters({ brands: ['kessler'], colours: ['charcoal'] })),
    ).toHaveLength(0);
  });

  it('keeps a group when only some of its offers match, and rebuilds it', () => {
    const cheap = makeProduct({
      product_id: 'cheap',
      retailer: 'harbour',
      retailer_name: 'Harbour & Hale',
      price: 99,
      total_price: 99,
    });
    const expensive = makeProduct({ product_id: 'dear', price: 200, total_price: 200 });
    const group = makeGroup({
      group_id: 'multi',
      offers: [expensive, cheap],
      offer_count: 2,
      lowest_total_price: 99,
    });

    const result = applyFilters([group], withFilters({ retailers: ['harbour'] }));
    expect(result).toHaveLength(1);
    expect(result[0]!.offer_count).toBe(1);
    expect(result[0]!.primary.retailer).toBe('harbour');
    expect(result[0]!.lowest_total_price).toBe(99);
  });

  it('drops a group when no offer survives', () => {
    expect(applyFilters(groups, withFilters({ retailers: ['nobody'] }))).toHaveLength(0);
  });

  it('prefers an in-stock offer as the rebuilt primary', () => {
    const cheapButGone = makeProduct({
      product_id: 'gone',
      price: 50,
      total_price: 50,
      in_stock: false,
    });
    const available = makeProduct({ product_id: 'here', price: 80, total_price: 80 });
    // A third offer that the filter removes, so the group is rebuilt rather
    // than passed through untouched.
    const tooExpensive = makeProduct({ product_id: 'dear', price: 500, total_price: 500 });
    const group = makeGroup({
      group_id: 'multi',
      primary: tooExpensive,
      offers: [tooExpensive, cheapButGone, available],
      offer_count: 3,
    });

    const result = applyFilters([group], withFilters({ priceRange: [0, 100] }));
    expect(result[0]!.offer_count).toBe(2);
    expect(result[0]!.primary.product_id).toBe('here');
    expect(result[0]!.lowest_total_price).toBe(80);
  });

  it('leaves a fully matching group untouched', () => {
    const result = applyFilters([shirt], emptyFilters);
    expect(result[0]).toBe(shirt);
  });
});

describe('sortGroups', () => {
  const groups = [shirt, trouser];

  it('sorts by relevance by default', () => {
    expect(sortGroups(groups, 'relevance').map((g) => g.group_id)).toEqual([
      'shirt',
      'trouser',
    ]);
  });

  it('sorts by lowest price', () => {
    expect(sortGroups(groups, 'price_low_to_high')[0]!.group_id).toBe('shirt');
  });

  it('sorts by biggest discount', () => {
    expect(sortGroups(groups, 'biggest_discount')[0]!.group_id).toBe('shirt');
  });

  it('sorts by newest', () => {
    const older = makeGroup(
      { group_id: 'older' },
      { product_id: 'older', source_updated_at: '2020-01-01T00:00:00Z' },
    );
    expect(sortGroups([older, shirt], 'newest')[0]!.group_id).toBe('shirt');
  });

  it('does not mutate the input array', () => {
    const input = [trouser, shirt];
    sortGroups(input, 'price_low_to_high');
    expect(input[0]!.group_id).toBe('trouser');
  });
});

describe('filter helpers', () => {
  it('counts active filters', () => {
    expect(countActiveFilters(emptyFilters)).toBe(0);
    expect(
      countActiveFilters(
        withFilters({ brands: ['a', 'b'], inStockOnly: true, priceRange: [0, 10] }),
      ),
    ).toBe(4);
  });

  it('toggles values case-insensitively', () => {
    expect(toggleValue([], 'Kessler')).toEqual(['kessler']);
    expect(toggleValue(['kessler'], 'Kessler')).toEqual([]);
  });
});
