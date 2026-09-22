/**
 * Mirrors the Pydantic models in `apps/api/app/models`.
 * Keep the two in step - `docs/api.md` is the contract.
 */

export type SortPreference = 'relevance' | 'price_low_to_high' | 'biggest_discount' | 'newest';

export type Gender = 'men' | 'women' | 'unisex';

export interface SearchIntent {
  original_query: string;
  product_categories: string[];
  occasion: string | null;
  styles: string[];
  colours: string[];
  materials: string[];
  fits: string[];
  brands: string[];
  excluded_brands: string[];
  size: string | null;
  minimum_price: number | null;
  maximum_price: number | null;
  currency: string;
  destination_country: string;
  destination_postcode: string | null;
  destination_city: string | null;
  gender: Gender;
  sort_preference: SortPreference;
  additional_keywords: string[];
}

export interface Product {
  product_id: string;
  title: string;
  description: string | null;
  brand: string | null;
  retailer: string;
  retailer_name: string | null;
  product_url: string;
  affiliate_url: string;
  image_url: string | null;
  category: string | null;
  colours: string[];
  materials: string[];
  available_sizes: string[];
  price: number;
  original_price: number | null;
  currency: string;
  in_stock: boolean;
  shipping_destination: string | null;
  shipping_cost: number | null;
  source_updated_at: string | null;
  retrieved_at: string;
  match_score: number;
  match_reasons: string[];
  discount_percent: number | null;
  total_price: number;
}

export interface ProductGroup {
  group_id: string;
  primary: Product;
  offers: Product[];
  match_score: number;
  match_reasons: string[];
  offer_count: number;
  retailers: string[];
  lowest_total_price: number;
}

export type RetailerState = 'pending' | 'running' | 'completed' | 'failed' | 'skipped';

export interface RetailerStatus {
  key: string;
  name: string;
  state: RetailerState;
  product_count: number;
  duration_ms: number | null;
  error: string | null;
  attempts: number;
}

export type SearchStatus = 'running' | 'completed' | 'partial' | 'failed';
export type CacheState = 'miss' | 'fresh' | 'stale' | 'refreshed' | 'coalesced';

export interface SearchCreated {
  search_id: string;
  query: string;
  status: string;
  events_url: string;
  snapshot_url: string;
}

export interface SearchSnapshot {
  search_id: string;
  query: string;
  intent: SearchIntent | Record<string, never>;
  groups: ProductGroup[];
  retailers: RetailerStatus[];
  status: SearchStatus;
  cache_state: CacheState;
  total_products: number;
  started_at: string;
  completed_at: string | null;
  results_updated_at: string | null;
  warnings: string[];
}

export type SearchEventName =
  | 'search_started'
  | 'intent_parsed'
  | 'retailer_started'
  | 'retailer_completed'
  | 'retailer_failed'
  | 'products_added'
  | 'ranking_completed'
  | 'search_completed';

interface EventEnvelope {
  sequence: number;
  type: SearchEventName;
  search_id: string;
  timestamp: string;
}

export interface SearchStartedEvent extends EventEnvelope {
  query: string;
  cache_state: CacheState;
  retailers: RetailerStatus[];
}

export interface IntentParsedEvent extends EventEnvelope {
  intent: SearchIntent;
  parser: string;
  duration_ms: number;
  retailers: RetailerStatus[];
}

export interface RetailerEvent extends EventEnvelope {
  retailer: RetailerStatus;
  error?: string;
}

export interface ProductsAddedEvent extends EventEnvelope {
  groups: ProductGroup[];
  total_products: number;
  source: 'live' | 'cache';
  results_updated_at: string | null;
}

export interface RankingCompletedEvent extends EventEnvelope {
  groups: ProductGroup[];
  total_products: number;
  group_count: number;
}

export interface SearchCompletedEvent extends EventEnvelope {
  status: SearchStatus;
  cache_state: CacheState;
  total_products: number;
  group_count: number;
  retailers: RetailerStatus[];
  warnings: string[];
  results_updated_at: string | null;
  duration_ms: number;
}

export interface RetailerSummary {
  key: string;
  name: string;
  type: string;
  ships_to: string[];
  currency: string;
  requires_permission: boolean;
  healthy: boolean | null;
  message: string | null;
  latency_ms: number | null;
}

export interface SavedSearch {
  id: string;
  label: string | null;
  query: string;
  intent: SearchIntent;
  intent_fingerprint: string;
  alerts_enabled: boolean;
  created_at: string | null;
  last_run_at: string | null;
}

export interface Favourite {
  id: string;
  retailer: string;
  product_id: string;
  group_id: string | null;
  title: string;
  product: Partial<Product>;
  price_at_save: number | null;
  currency: string;
  created_at: string | null;
}
