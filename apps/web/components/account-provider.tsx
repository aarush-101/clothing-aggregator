'use client';

import * as React from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  ApiError,
  addFavourite,
  createAnonymousSession,
  deleteSavedSearch,
  listFavourites,
  listSavedSearches,
  removeFavourite,
  saveSearch as saveSearchRequest,
} from '@/lib/api';
import type { Favourite, Product, SavedSearch } from '@/lib/types';

const TOKEN_KEY = 'marle.account-token';

function readToken(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

const tokenListeners = new Set<() => void>();

function writeToken(token: string): void {
  try {
    window.localStorage.setItem(TOKEN_KEY, token);
  } catch {
    /* private browsing - the session simply will not persist */
  }
  for (const listener of tokenListeners) listener();
}

function subscribeToToken(onChange: () => void): () => void {
  tokenListeners.add(onChange);
  window.addEventListener('storage', onChange);
  return () => {
    tokenListeners.delete(onChange);
    window.removeEventListener('storage', onChange);
  };
}

/**
 * The token lives in localStorage, which is an external store rather than
 * React state - reading it through useSyncExternalStore keeps the server
 * render (always null) and the client in step without a mount effect.
 */
function useStoredToken(): string | null {
  return React.useSyncExternalStore(
    subscribeToToken,
    readToken,
    () => null,
  );
}

export function favouriteKey(retailer: string, productId: string): string {
  return `${retailer}:${productId}`;
}

interface AccountContextValue {
  token: string | null;
  /** False once the API has told us accounts are not configured. */
  available: boolean;
  favourites: Favourite[];
  favouriteKeys: Set<string>;
  savedSearches: SavedSearch[];
  isFavourite: (retailer: string, productId: string) => boolean;
  toggleFavourite: (product: Product, groupId: string | null) => void;
  /** Removes a favourite by identity, for views that never held the product. */
  unfavourite: (retailer: string, productId: string) => void;
  saveSearch: (query: string, label?: string) => void;
  removeSavedSearch: (id: string) => void;
  pending: boolean;
  error: string | null;
}

const AccountContext = React.createContext<AccountContextValue | null>(null);

export function AccountProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  const token = useStoredToken();
  const [available, setAvailable] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  const ensureToken = React.useCallback(async (): Promise<string> => {
    const existing = readToken();
    if (existing) return existing;
    const session = await createAnonymousSession();
    writeToken(session.token);
    return session.token;
  }, []);

  const handleError = React.useCallback((cause: unknown) => {
    if (cause instanceof ApiError && cause.status === 501) {
      setAvailable(false);
      setError('Saving needs a database. Set DATABASE_URL on the API to enable it.');
      return;
    }
    setError(cause instanceof ApiError ? cause.message : 'Something went wrong. Try again.');
  }, []);

  const favouritesQuery = useQuery({
    queryKey: ['favourites', token],
    queryFn: () => listFavourites(token as string),
    enabled: Boolean(token) && available,
  });

  const savedSearchesQuery = useQuery({
    queryKey: ['saved-searches', token],
    queryFn: () => listSavedSearches(token as string),
    enabled: Boolean(token) && available,
  });

  const favourites = React.useMemo(
    () => favouritesQuery.data ?? [],
    [favouritesQuery.data],
  );

  const favouriteKeys = React.useMemo(
    () => new Set(favourites.map((item) => favouriteKey(item.retailer, item.product_id))),
    [favourites],
  );

  const invalidate = React.useCallback(
    (key: string) => {
      void queryClient.invalidateQueries({ queryKey: [key] });
    },
    [queryClient],
  );

  const toggleMutation = useMutation({
    mutationFn: async ({
      product,
      groupId,
      remove,
    }: {
      product: Pick<Product, 'retailer' | 'product_id'> & Partial<Product>;
      groupId: string | null;
      remove: boolean;
    }) => {
      const activeToken = await ensureToken();
      if (remove) {
        await removeFavourite(activeToken, product.retailer, product.product_id);
      } else {
        await addFavourite(activeToken, product as Product, groupId);
      }
    },
    onSuccess: () => {
      setError(null);
      invalidate('favourites');
    },
    onError: handleError,
  });

  const saveSearchMutation = useMutation({
    mutationFn: async ({ query, label }: { query: string; label?: string }) => {
      const activeToken = await ensureToken();
      await saveSearchRequest(activeToken, query, label);
    },
    onSuccess: () => {
      setError(null);
      invalidate('saved-searches');
    },
    onError: handleError,
  });

  const removeSavedSearchMutation = useMutation({
    mutationFn: async (id: string) => {
      const activeToken = await ensureToken();
      await deleteSavedSearch(activeToken, id);
    },
    onSuccess: () => invalidate('saved-searches'),
    onError: handleError,
  });

  const value = React.useMemo<AccountContextValue>(
    () => ({
      token,
      available,
      favourites,
      favouriteKeys,
      savedSearches: savedSearchesQuery.data ?? [],
      isFavourite: (retailer, productId) =>
        favouriteKeys.has(favouriteKey(retailer, productId)),
      toggleFavourite: (product, groupId) =>
        toggleMutation.mutate({
          product,
          groupId,
          remove: favouriteKeys.has(favouriteKey(product.retailer, product.product_id)),
        }),
      unfavourite: (retailer, productId) =>
        toggleMutation.mutate({
          product: { retailer, product_id: productId },
          groupId: null,
          remove: true,
        }),
      saveSearch: (query, label) => saveSearchMutation.mutate({ query, label }),
      removeSavedSearch: (id) => removeSavedSearchMutation.mutate(id),
      pending:
        toggleMutation.isPending ||
        saveSearchMutation.isPending ||
        removeSavedSearchMutation.isPending,
      error,
    }),
    [
      token,
      available,
      favourites,
      favouriteKeys,
      savedSearchesQuery.data,
      toggleMutation,
      saveSearchMutation,
      removeSavedSearchMutation,
      error,
    ],
  );

  return <AccountContext.Provider value={value}>{children}</AccountContext.Provider>;
}

export function useAccount(): AccountContextValue {
  const context = React.useContext(AccountContext);
  if (!context) {
    throw new Error('useAccount must be used inside <AccountProvider>');
  }
  return context;
}
