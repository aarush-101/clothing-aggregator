'use client';

import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react';

import { ApiError, createSearch, getSearchSnapshot, searchEventsUrl } from './api';
import type {
  CacheState,
  IntentParsedEvent,
  ProductGroup,
  ProductsAddedEvent,
  RankingCompletedEvent,
  RetailerEvent,
  RetailerStatus,
  SearchCompletedEvent,
  SearchCreated,
  SearchIntent,
  SearchSnapshot,
  SearchStartedEvent,
  SearchStatus,
} from './types';

export type SearchPhase = 'idle' | 'starting' | 'streaming' | 'settled' | 'error';

export interface SearchStreamState {
  phase: SearchPhase;
  searchId: string | null;
  query: string;
  intent: SearchIntent | null;
  parser: string | null;
  retailers: RetailerStatus[];
  groups: ProductGroup[];
  totalProducts: number;
  status: SearchStatus | null;
  cacheState: CacheState | null;
  warnings: string[];
  resultsUpdatedAt: string | null;
  servedFromCache: boolean;
  reconnecting: boolean;
  durationMs: number | null;
  error: string | null;
}

const initialState: SearchStreamState = {
  phase: 'idle',
  searchId: null,
  query: '',
  intent: null,
  parser: null,
  retailers: [],
  groups: [],
  totalProducts: 0,
  status: null,
  cacheState: null,
  warnings: [],
  resultsUpdatedAt: null,
  servedFromCache: false,
  reconnecting: false,
  durationMs: null,
  error: null,
};

type Action =
  | { type: 'reset'; query: string }
  | { type: 'created'; searchId: string }
  | { type: 'started'; payload: SearchStartedEvent }
  | { type: 'intent'; payload: IntentParsedEvent }
  | { type: 'retailer'; payload: RetailerEvent }
  | { type: 'products'; payload: ProductsAddedEvent }
  | { type: 'ranked'; payload: RankingCompletedEvent }
  | { type: 'completed'; payload: SearchCompletedEvent }
  | { type: 'snapshot'; payload: SearchSnapshot }
  | { type: 'reconnecting'; value: boolean }
  | { type: 'error'; message: string };

/**
 * Merge incrementally streamed groups into the current list.
 * Groups are keyed by `group_id`, so a retailer arriving late updates the
 * existing card (adding its offer) instead of duplicating it.
 */
export function mergeGroups(existing: ProductGroup[], incoming: ProductGroup[]): ProductGroup[] {
  if (incoming.length === 0) return existing;
  const byId = new Map(existing.map((group) => [group.group_id, group]));
  for (const group of incoming) {
    byId.set(group.group_id, group);
  }
  return [...byId.values()].sort(
    (a, b) => b.match_score - a.match_score || a.lowest_total_price - b.lowest_total_price,
  );
}

function upsertRetailer(
  retailers: RetailerStatus[],
  incoming: RetailerStatus,
): RetailerStatus[] {
  const index = retailers.findIndex((retailer) => retailer.key === incoming.key);
  if (index === -1) return [...retailers, incoming];
  const next = [...retailers];
  next[index] = incoming;
  return next;
}

function reducer(state: SearchStreamState, action: Action): SearchStreamState {
  switch (action.type) {
    case 'reset':
      return { ...initialState, query: action.query, phase: 'starting' };
    case 'created':
      return { ...state, searchId: action.searchId, phase: 'streaming' };
    case 'started':
      return { ...state, retailers: action.payload.retailers, phase: 'streaming' };
    case 'intent':
      return {
        ...state,
        intent: action.payload.intent,
        parser: action.payload.parser,
        retailers: action.payload.retailers,
      };
    case 'retailer':
      return { ...state, retailers: upsertRetailer(state.retailers, action.payload.retailer) };
    case 'products':
      return {
        ...state,
        groups: mergeGroups(state.groups, action.payload.groups),
        totalProducts: action.payload.total_products,
        resultsUpdatedAt: action.payload.results_updated_at ?? state.resultsUpdatedAt,
        servedFromCache: state.servedFromCache || action.payload.source === 'cache',
      };
    case 'ranked':
      return {
        ...state,
        // The authoritative ordered result set replaces the streamed one.
        groups: action.payload.groups,
        totalProducts: action.payload.total_products,
      };
    case 'completed':
      return {
        ...state,
        phase: 'settled',
        status: action.payload.status,
        cacheState: action.payload.cache_state,
        retailers: action.payload.retailers,
        warnings: action.payload.warnings,
        totalProducts: action.payload.total_products,
        resultsUpdatedAt: action.payload.results_updated_at ?? state.resultsUpdatedAt,
        durationMs: action.payload.duration_ms,
        reconnecting: false,
        error: null,
      };
    case 'snapshot':
      return {
        ...state,
        phase: 'settled',
        groups: action.payload.groups,
        retailers: action.payload.retailers,
        status: action.payload.status,
        cacheState: action.payload.cache_state,
        warnings: action.payload.warnings,
        totalProducts: action.payload.total_products,
        resultsUpdatedAt: action.payload.results_updated_at,
        intent:
          action.payload.intent && 'original_query' in action.payload.intent
            ? (action.payload.intent as SearchIntent)
            : state.intent,
        reconnecting: false,
        error: null,
      };
    case 'reconnecting':
      return { ...state, reconnecting: action.value };
    case 'error':
      return { ...state, phase: 'error', reconnecting: false, error: action.message };
    default:
      return state;
  }
}

function parseEvent<T>(event: MessageEvent): T | null {
  try {
    return JSON.parse(event.data) as T;
  } catch {
    return null;
  }
}

/**
 * Runs one search and streams its progress.
 *
 * Creates the search job, subscribes to its Server-Sent Events, and falls back
 * to the snapshot endpoint if the stream drops before the search finishes.
 */
export function useSearchStream(query: string) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const [attempt, setAttempt] = useState(0);
  const settledRef = useRef(false);
  // Shared across React Strict Mode's double effect invocation so a single
  // search job is created per query rather than two.
  const pendingCreates = useRef(new Map<string, Promise<SearchCreated>>());

  const retry = useCallback(() => setAttempt((value) => value + 1), []);

  useEffect(() => {
    const trimmed = query.trim();
    if (!trimmed) return;

    let cancelled = false;
    let source: EventSource | null = null;
    settledRef.current = false;
    dispatch({ type: 'reset', query: trimmed });

    const key = `${trimmed}::${attempt}`;
    let create = pendingCreates.current.get(key);
    if (!create) {
      create = createSearch(trimmed);
      pendingCreates.current.set(key, create);
    }

    const fallbackToSnapshot = async (searchId: string) => {
      try {
        const snapshot = await getSearchSnapshot(searchId);
        if (!cancelled) dispatch({ type: 'snapshot', payload: snapshot });
      } catch {
        if (!cancelled) {
          dispatch({
            type: 'error',
            message: 'The connection dropped before results finished loading.',
          });
        }
      }
    };

    create
      .then((created) => {
        if (cancelled) return;
        dispatch({ type: 'created', searchId: created.search_id });

        source = new EventSource(searchEventsUrl(created.search_id));

        source.addEventListener('open', () => dispatch({ type: 'reconnecting', value: false }));

        source.addEventListener('search_started', (event) => {
          const payload = parseEvent<SearchStartedEvent>(event as MessageEvent);
          if (payload) dispatch({ type: 'started', payload });
        });

        source.addEventListener('intent_parsed', (event) => {
          const payload = parseEvent<IntentParsedEvent>(event as MessageEvent);
          if (payload) dispatch({ type: 'intent', payload });
        });

        for (const name of [
          'retailer_started',
          'retailer_completed',
          'retailer_failed',
        ] as const) {
          source.addEventListener(name, (event) => {
            const payload = parseEvent<RetailerEvent>(event as MessageEvent);
            if (payload) dispatch({ type: 'retailer', payload });
          });
        }

        source.addEventListener('products_added', (event) => {
          const payload = parseEvent<ProductsAddedEvent>(event as MessageEvent);
          if (payload) dispatch({ type: 'products', payload });
        });

        source.addEventListener('ranking_completed', (event) => {
          const payload = parseEvent<RankingCompletedEvent>(event as MessageEvent);
          if (payload) dispatch({ type: 'ranked', payload });
        });

        source.addEventListener('search_completed', (event) => {
          const payload = parseEvent<SearchCompletedEvent>(event as MessageEvent);
          if (payload) dispatch({ type: 'completed', payload });
          settledRef.current = true;
          source?.close();
        });

        source.addEventListener('error', () => {
          // The server closes the stream once the search completes; the
          // browser reports that as an error, which we ignore.
          if (settledRef.current || cancelled) return;
          if (source?.readyState === EventSource.CLOSED) {
            void fallbackToSnapshot(created.search_id);
          } else {
            dispatch({ type: 'reconnecting', value: true });
          }
        });
      })
      .catch((error: unknown) => {
        pendingCreates.current.delete(key);
        if (cancelled) return;
        const message =
          error instanceof ApiError
            ? error.message
            : 'Something went wrong starting your search.';
        dispatch({ type: 'error', message });
      });

    return () => {
      cancelled = true;
      source?.close();
    };
  }, [query, attempt]);

  const activeRetailers = useMemo(
    () => state.retailers.filter((retailer) => retailer.state !== 'skipped'),
    [state.retailers],
  );

  const failedRetailers = useMemo(
    () => activeRetailers.filter((retailer) => retailer.state === 'failed'),
    [activeRetailers],
  );

  const isLoading = state.phase === 'starting' || state.phase === 'streaming';

  return { ...state, activeRetailers, failedRetailers, isLoading, retry };
}
