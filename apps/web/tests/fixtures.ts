import type { Product, ProductGroup, SearchIntent } from '@/lib/types';

export function makeProduct(overrides: Partial<Product> = {}): Product {
  return {
    product_id: 'p1',
    title: 'Kessler Relaxed Linen Shirt',
    description: 'A relaxed black linen shirt.',
    brand: 'Kessler',
    retailer: 'northbound',
    retailer_name: 'Northbound Supply',
    product_url: 'https://northbound-supply.example/products/kessler-shirt',
    image_url: 'https://images.example/kessler-shirt.jpg',
    category: 'shirt',
    colours: ['black'],
    materials: ['linen'],
    available_sizes: ['s', 'm', 'l'],
    price: 119,
    original_price: 149,
    currency: 'AUD',
    in_stock: true,
    shipping_destination: 'AU',
    shipping_cost: 0,
    source_updated_at: '2026-09-21T00:00:00+00:00',
    retrieved_at: '2026-09-22T00:00:00+00:00',
    match_score: 0.92,
    match_reasons: ['Matches your requested black colour and linen material.'],
    discount_percent: 20,
    total_price: 119,
    ...overrides,
  };
}

export function makeGroup(
  overrides: Partial<ProductGroup> = {},
  productOverrides: Partial<Product> = {},
): ProductGroup {
  const primary = makeProduct(productOverrides);
  return {
    group_id: `g-${primary.retailer}-${primary.product_id}`,
    primary,
    offers: [primary],
    match_score: primary.match_score,
    match_reasons: primary.match_reasons,
    offer_count: 1,
    retailers: [primary.retailer_name ?? primary.retailer],
    lowest_total_price: primary.total_price,
    ...overrides,
  };
}

export function makeIntent(overrides: Partial<SearchIntent> = {}): SearchIntent {
  return {
    original_query: 'relaxed black linen shirt under $120',
    product_categories: ['shirt'],
    occasion: null,
    styles: [],
    colours: ['black'],
    materials: ['linen'],
    fits: ['relaxed'],
    brands: [],
    excluded_brands: [],
    size: null,
    minimum_price: null,
    maximum_price: 120,
    currency: 'AUD',
    destination_country: 'AU',
    destination_postcode: null,
    destination_city: 'Sydney',
    gender: 'men',
    sort_preference: 'relevance',
    additional_keywords: [],
    ...overrides,
  };
}
