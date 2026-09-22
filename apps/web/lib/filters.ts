/**
 * Client-side faceting, filtering and sorting.
 *
 * Refinement happens in the browser over the result set the backend already
 * ranked, so changing a filter is instant and does not re-query retailers.
 */

import type { Product, ProductGroup, SortPreference } from './types';

export interface FacetValue {
  value: string;
  label: string;
  count: number;
}

export interface Facets {
  brands: FacetValue[];
  retailers: FacetValue[];
  colours: FacetValue[];
  sizes: FacetValue[];
  materials: FacetValue[];
  priceMin: number;
  priceMax: number;
  hasDiscounts: boolean;
  hasOutOfStock: boolean;
}

export interface FilterState {
  brands: string[];
  retailers: string[];
  colours: string[];
  sizes: string[];
  materials: string[];
  priceRange: [number, number] | null;
  inStockOnly: boolean;
  onSaleOnly: boolean;
}

export type FilterKey = 'brands' | 'retailers' | 'colours' | 'sizes' | 'materials';

export const emptyFilters: FilterState = {
  brands: [],
  retailers: [],
  colours: [],
  sizes: [],
  materials: [],
  priceRange: null,
  inStockOnly: false,
  onSaleOnly: false,
};

const SIZE_ORDER = ['xs', 's', 'm', 'l', 'xl', 'xxl', 'xxxl'];

function increment(map: Map<string, FacetValue>, value: string, label: string): void {
  const key = value.toLowerCase();
  const existing = map.get(key);
  if (existing) {
    existing.count += 1;
  } else {
    map.set(key, { value: key, label, count: 1 });
  }
}

function byCountThenLabel(a: FacetValue, b: FacetValue): number {
  return b.count - a.count || a.label.localeCompare(b.label);
}

function sizeSort(a: FacetValue, b: FacetValue): number {
  const aIndex = SIZE_ORDER.indexOf(a.value);
  const bIndex = SIZE_ORDER.indexOf(b.value);
  if (aIndex !== -1 && bIndex !== -1) return aIndex - bIndex;
  if (aIndex !== -1) return -1;
  if (bIndex !== -1) return 1;
  const aNumber = Number(a.value);
  const bNumber = Number(b.value);
  if (Number.isFinite(aNumber) && Number.isFinite(bNumber)) return aNumber - bNumber;
  return a.label.localeCompare(b.label);
}

export function buildFacets(groups: ProductGroup[]): Facets {
  const brands = new Map<string, FacetValue>();
  const retailers = new Map<string, FacetValue>();
  const colours = new Map<string, FacetValue>();
  const sizes = new Map<string, FacetValue>();
  const materials = new Map<string, FacetValue>();

  let priceMin = Number.POSITIVE_INFINITY;
  let priceMax = 0;
  let hasDiscounts = false;
  let hasOutOfStock = false;

  for (const group of groups) {
    // Garment-level facets are counted once per card, not once per offer.
    if (group.primary.brand) increment(brands, group.primary.brand, group.primary.brand);
    for (const colour of group.primary.colours) increment(colours, colour, colour);
    for (const material of group.primary.materials) increment(materials, material, material);

    for (const offer of group.offers) {
      increment(retailers, offer.retailer, offer.retailer_name ?? offer.retailer);
      for (const size of offer.available_sizes) increment(sizes, size, size.toUpperCase());
      priceMin = Math.min(priceMin, offer.price);
      priceMax = Math.max(priceMax, offer.price);
      if ((offer.discount_percent ?? 0) > 0) hasDiscounts = true;
      if (!offer.in_stock) hasOutOfStock = true;
    }
  }

  return {
    brands: [...brands.values()].sort(byCountThenLabel),
    retailers: [...retailers.values()].sort(byCountThenLabel),
    colours: [...colours.values()].sort(byCountThenLabel),
    sizes: [...sizes.values()].sort(sizeSort),
    materials: [...materials.values()].sort(byCountThenLabel),
    priceMin: Number.isFinite(priceMin) ? Math.floor(priceMin) : 0,
    priceMax: Math.ceil(priceMax),
    hasDiscounts,
    hasOutOfStock,
  };
}

function lowercase(values: string[]): string[] {
  return values.map((value) => value.toLowerCase());
}

function offerMatches(offer: Product, filters: FilterState): boolean {
  if (filters.inStockOnly && !offer.in_stock) return false;
  if (filters.onSaleOnly && !(offer.discount_percent ?? 0)) return false;

  if (filters.retailers.length && !filters.retailers.includes(offer.retailer.toLowerCase())) {
    return false;
  }

  if (filters.sizes.length) {
    const available = lowercase(offer.available_sizes);
    if (!filters.sizes.some((size) => available.includes(size))) return false;
  }

  if (filters.priceRange) {
    const [min, max] = filters.priceRange;
    if (offer.price < min || offer.price > max) return false;
  }

  return true;
}

function garmentMatches(group: ProductGroup, filters: FilterState): boolean {
  const { primary } = group;

  if (filters.brands.length) {
    const brand = (primary.brand ?? '').toLowerCase();
    if (!filters.brands.includes(brand)) return false;
  }

  if (filters.colours.length) {
    const colours = lowercase(primary.colours);
    if (!filters.colours.some((colour) => colours.includes(colour))) return false;
  }

  if (filters.materials.length) {
    const materials = lowercase(primary.materials);
    if (!filters.materials.some((material) => materials.includes(material))) return false;
  }

  return true;
}

function offerRank(offer: Product): number {
  // In-stock first, then cheapest including shipping - the same rule the
  // backend uses when it picks a group's primary offer.
  return (offer.in_stock ? 0 : 1_000_000) + offer.total_price;
}

function rebuildGroup(group: ProductGroup, offers: Product[]): ProductGroup {
  const sorted = [...offers].sort((a, b) => offerRank(a) - offerRank(b));
  const primary = sorted[0] ?? group.primary;
  const purchasable = sorted.filter((offer) => offer.in_stock);
  const priced = purchasable.length ? purchasable : sorted;
  return {
    ...group,
    primary,
    offers: sorted,
    offer_count: sorted.length,
    retailers: [...new Set(sorted.map((offer) => offer.retailer_name ?? offer.retailer))],
    lowest_total_price: Math.min(...priced.map((offer) => offer.total_price)),
  };
}

export function applyFilters(groups: ProductGroup[], filters: FilterState): ProductGroup[] {
  const result: ProductGroup[] = [];
  for (const group of groups) {
    if (!garmentMatches(group, filters)) continue;
    const offers = group.offers.filter((offer) => offerMatches(offer, filters));
    if (offers.length === 0) continue;
    result.push(offers.length === group.offers.length ? group : rebuildGroup(group, offers));
  }
  return result;
}

function bestDiscount(group: ProductGroup): number {
  return group.offers.reduce((best, offer) => Math.max(best, offer.discount_percent ?? 0), 0);
}

function newestTimestamp(group: ProductGroup): number {
  return group.offers.reduce((newest, offer) => {
    const value = Date.parse(offer.source_updated_at ?? offer.retrieved_at);
    return Number.isNaN(value) ? newest : Math.max(newest, value);
  }, 0);
}

export function sortGroups(groups: ProductGroup[], sort: SortPreference): ProductGroup[] {
  const sorted = [...groups];
  switch (sort) {
    case 'price_low_to_high':
      return sorted.sort(
        (a, b) => a.lowest_total_price - b.lowest_total_price || b.match_score - a.match_score,
      );
    case 'biggest_discount':
      return sorted.sort(
        (a, b) => bestDiscount(b) - bestDiscount(a) || b.match_score - a.match_score,
      );
    case 'newest':
      return sorted.sort(
        (a, b) => newestTimestamp(b) - newestTimestamp(a) || b.match_score - a.match_score,
      );
    default:
      return sorted.sort(
        (a, b) =>
          b.match_score - a.match_score || a.lowest_total_price - b.lowest_total_price,
      );
  }
}

export function countActiveFilters(filters: FilterState): number {
  return (
    filters.brands.length +
    filters.retailers.length +
    filters.colours.length +
    filters.sizes.length +
    filters.materials.length +
    (filters.priceRange ? 1 : 0) +
    (filters.inStockOnly ? 1 : 0) +
    (filters.onSaleOnly ? 1 : 0)
  );
}

export function toggleValue(values: string[], value: string): string[] {
  const lowered = value.toLowerCase();
  return values.includes(lowered)
    ? values.filter((item) => item !== lowered)
    : [...values, lowered];
}
