import type {
  Favourite,
  Product,
  RetailerSummary,
  SavedSearch,
  SearchCreated,
  SearchSnapshot,
} from './types';

export const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://localhost:8000'
).replace(/\/$/, '');

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(message: string, status: number, code = 'error') {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

interface ErrorBody {
  error?: string;
  detail?: string;
  fields?: { field: string; message: string }[];
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        ...(init.headers ?? {}),
      },
    });
  } catch {
    throw new ApiError(
      'Could not reach the search service. Check your connection and try again.',
      0,
      'network_error',
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const text = await response.text();
  const body: unknown = text ? safeJsonParse(text) : null;

  if (!response.ok) {
    const error = (body ?? {}) as ErrorBody;
    const detail =
      error.fields?.[0]?.message ?? error.detail ?? `Request failed (${response.status})`;
    throw new ApiError(detail, response.status, error.error ?? 'error');
  }

  return body as T;
}

function safeJsonParse(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function authHeaders(token: string | null): Record<string, string> {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export function createSearch(query: string): Promise<SearchCreated> {
  return request<SearchCreated>('/api/search', {
    method: 'POST',
    body: JSON.stringify({ query }),
  });
}

export function getSearchSnapshot(searchId: string): Promise<SearchSnapshot> {
  return request<SearchSnapshot>(`/api/search/${encodeURIComponent(searchId)}`);
}

export function searchEventsUrl(searchId: string): string {
  return `${API_BASE_URL}/api/search/${encodeURIComponent(searchId)}/events`;
}

export function listRetailers(includeHealth = false): Promise<RetailerSummary[]> {
  return request<RetailerSummary[]>(
    `/api/retailers${includeHealth ? '?include_health=true' : ''}`,
  );
}

export interface ClickPayload {
  retailer: string;
  product_id: string;
  destination_url: string;
  search_id?: string;
  price?: number;
  currency?: string;
  position?: number;
}

/**
 * Records an outbound click. Fire-and-forget: the shopper is already on their
 * way to the retailer, so a failure here must never surface as an error.
 */
export function recordClick(payload: ClickPayload, token: string | null = null): void {
  void request('/api/clicks', {
    method: 'POST',
    body: JSON.stringify(payload),
    headers: authHeaders(token),
    keepalive: true,
  }).catch(() => undefined);
}

export function createAnonymousSession(): Promise<{
  user_id: string;
  token: string;
  is_anonymous: boolean;
}> {
  return request('/api/auth/session', { method: 'POST' });
}

export function listSavedSearches(token: string): Promise<SavedSearch[]> {
  return request<SavedSearch[]>('/api/account/saved-searches', {
    headers: authHeaders(token),
  });
}

export function saveSearch(
  token: string,
  query: string,
  label?: string,
): Promise<SavedSearch> {
  return request<SavedSearch>('/api/account/saved-searches', {
    method: 'POST',
    body: JSON.stringify({ query, label: label ?? null }),
    headers: authHeaders(token),
  });
}

export function deleteSavedSearch(token: string, id: string): Promise<void> {
  return request<void>(`/api/account/saved-searches/${encodeURIComponent(id)}`, {
    method: 'DELETE',
    headers: authHeaders(token),
  });
}

export function listFavourites(token: string): Promise<Favourite[]> {
  return request<Favourite[]>('/api/account/favourites', { headers: authHeaders(token) });
}

export function addFavourite(
  token: string,
  product: Product,
  groupId: string | null,
): Promise<Favourite> {
  return request<Favourite>('/api/account/favourites', {
    method: 'POST',
    body: JSON.stringify({ product, group_id: groupId }),
    headers: authHeaders(token),
  });
}

export function removeFavourite(
  token: string,
  retailer: string,
  productId: string,
): Promise<void> {
  return request<void>(
    `/api/account/favourites/${encodeURIComponent(retailer)}/${encodeURIComponent(productId)}`,
    { method: 'DELETE', headers: authHeaders(token) },
  );
}
