'use client';

import Link from 'next/link';
import { Bookmark, Heart } from 'lucide-react';

import { useAccount } from '@/components/account-provider';
import { SearchBar } from '@/components/search-bar';
import { Wordmark } from '@/components/wordmark';
import { Button } from '@/components/ui/button';

export function ResultsHeader({ query }: { query: string }) {
  const { saveSearch, savedSearches, pending, available } = useAccount();
  const alreadySaved = savedSearches.some((saved) => saved.query === query);

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/92 backdrop-blur-sm">
      <div className="mx-auto flex max-w-[84rem] items-center gap-3 px-5 py-3 sm:gap-5">
        <Wordmark className="shrink-0" />
        <div className="min-w-0 flex-1">
          <SearchBar initialQuery={query} />
        </div>
        <div className="hidden shrink-0 items-center gap-1 sm:flex">
          {available && query ? (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => saveSearch(query)}
              disabled={pending || alreadySaved}
              aria-label={alreadySaved ? 'Search already saved' : 'Save this search'}
            >
              <Bookmark
                aria-hidden="true"
                className="size-4"
                fill={alreadySaved ? 'currentColor' : 'none'}
              />
              {alreadySaved ? 'Saved' : 'Save'}
            </Button>
          ) : null}
          <Button variant="ghost" size="icon" asChild>
            <Link href="/saved" aria-label="Saved searches and favourites">
              <Heart className="size-4" aria-hidden="true" />
            </Link>
          </Button>
        </div>
      </div>
    </header>
  );
}
