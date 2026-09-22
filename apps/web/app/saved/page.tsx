'use client';

import Link from 'next/link';
import { ArrowUpRight, Trash2 } from 'lucide-react';

import { useAccount } from '@/components/account-provider';
import { Wordmark } from '@/components/wordmark';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { formatPriceCompact } from '@/lib/format';

export default function SavedPage() {
  const {
    savedSearches,
    favourites,
    available,
    error,
    removeSavedSearch,
    unfavourite,
  } = useAccount();

  return (
    <div className="min-h-dvh">
      <header className="border-b border-border">
        <div className="mx-auto flex max-w-4xl items-center justify-between px-5 py-4">
          <Wordmark />
          <Button variant="ghost" size="sm" asChild>
            <Link href="/">New search</Link>
          </Button>
        </div>
      </header>

      <main id="main" className="mx-auto max-w-4xl px-5 py-12">
        <h1 className="font-serif text-2xl">Saved</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Saved searches and favourites are tied to this browser. Searching never requires an
          account.
        </p>

        {!available ? (
          <p className="mt-8 rounded-sm border border-dashed border-border-strong px-5 py-6 text-sm text-muted-foreground">
            Accounts are not enabled on this deployment. Set <code>DATABASE_URL</code> on the
            API to turn them on.
          </p>
        ) : null}
        {error ? <p className="mt-6 text-sm text-destructive">{error}</p> : null}

        <section className="mt-10">
          <h2 className="label-eyebrow">Saved searches</h2>
          <Separator className="mt-3" />
          {savedSearches.length === 0 ? (
            <p className="py-6 text-sm text-muted-foreground">No saved searches yet.</p>
          ) : (
            <ul className="divide-y divide-border">
              {savedSearches.map((saved) => (
                <li key={saved.id} className="flex items-center justify-between gap-4 py-4">
                  <Link
                    href={`/search?q=${encodeURIComponent(saved.query)}`}
                    className="min-w-0 flex-1 text-sm hover:underline"
                  >
                    <span className="truncate">{saved.label ?? saved.query}</span>
                  </Link>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={`Delete saved search: ${saved.query}`}
                    onClick={() => removeSavedSearch(saved.id)}
                  >
                    <Trash2 className="size-4" aria-hidden="true" />
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="mt-12">
          <h2 className="label-eyebrow">Favourites</h2>
          <Separator className="mt-3" />
          {favourites.length === 0 ? (
            <p className="py-6 text-sm text-muted-foreground">No favourites yet.</p>
          ) : (
            <ul className="divide-y divide-border">
              {favourites.map((favourite) => (
                <li key={favourite.id} className="flex items-center justify-between gap-4 py-4">
                  <div className="min-w-0">
                    <p className="truncate text-sm">{favourite.title}</p>
                    <p className="text-xs text-muted-foreground">
                      {favourite.retailer}
                      {favourite.price_at_save
                        ? ` · ${formatPriceCompact(favourite.price_at_save, favourite.currency)} when saved`
                        : ''}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    {favourite.product?.affiliate_url ? (
                      <Button variant="ghost" size="sm" asChild>
                        <a
                          href={favourite.product.affiliate_url}
                          target="_blank"
                          rel="noopener noreferrer nofollow sponsored"
                        >
                          View
                          <ArrowUpRight className="size-3.5" aria-hidden="true" />
                        </a>
                      </Button>
                    ) : null}
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={`Remove ${favourite.title} from favourites`}
                      onClick={() => unfavourite(favourite.retailer, favourite.product_id)}
                    >
                      <Trash2 className="size-4" aria-hidden="true" />
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </main>
    </div>
  );
}
