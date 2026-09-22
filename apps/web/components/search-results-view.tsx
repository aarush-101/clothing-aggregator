'use client';

import * as React from 'react';
import { useSearchParams } from 'next/navigation';
import { SlidersHorizontal } from 'lucide-react';

import { FilterPanel } from '@/components/filter-panel';
import { ProductCard, ProductCardSkeleton } from '@/components/product-card';
import { IntentChips } from '@/components/intent-chips';
import { ResultsHeader } from '@/components/results-header';
import { RetailerProgress } from '@/components/retailer-progress';
import {
  EmptyResults,
  NoFilterMatches,
  PartialResultsNotice,
  ReconnectingNotice,
  SearchFailure,
  StartSearchPrompt,
} from '@/components/result-states';
import { SortSelect } from '@/components/sort-select';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from '@/components/ui/sheet';
import { formatRelativeTime, pluralise } from '@/lib/format';
import {
  applyFilters,
  buildFacets,
  countActiveFilters,
  emptyFilters,
  sortGroups,
  type FilterState,
} from '@/lib/filters';
import type { SortPreference } from '@/lib/types';
import { useSearchStream } from '@/lib/use-search-stream';

const SKELETON_COUNT = 6;

export function SearchResultsView() {
  const searchParams = useSearchParams();
  const query = (searchParams.get('q') ?? '').trim();

  const stream = useSearchStream(query);
  const [filters, setFilters] = React.useState<FilterState>(emptyFilters);
  const [chosenSort, setChosenSort] = React.useState<SortPreference | null>(null);
  const [sheetOpen, setSheetOpen] = React.useState(false);
  const [syncedQuery, setSyncedQuery] = React.useState(query);

  // A new query starts from a clean slate. Adjusted during render rather than
  // in an effect (https://react.dev/learn/you-might-not-need-an-effect).
  if (query !== syncedQuery) {
    setSyncedQuery(query);
    setFilters(emptyFilters);
    setChosenSort(null);
  }

  // "…but cheaper" has to actually reorder the results, so the parsed
  // preference is the default until the shopper picks something else.
  const sort: SortPreference = chosenSort ?? stream.intent?.sort_preference ?? 'relevance';

  const facets = React.useMemo(() => buildFacets(stream.groups), [stream.groups]);
  const visibleGroups = React.useMemo(
    () => sortGroups(applyFilters(stream.groups, filters), sort),
    [stream.groups, filters, sort],
  );

  const activeFilterCount = countActiveFilters(filters);
  const resetFilters = React.useCallback(() => setFilters(emptyFilters), []);

  const showSkeletons = stream.isLoading && stream.groups.length === 0;
  const settled = stream.phase === 'settled';
  const noResults = settled && stream.groups.length === 0;
  const filteredEverythingOut =
    settled && stream.groups.length > 0 && visibleGroups.length === 0;

  const renderFilterPanel = (idPrefix: string) => (
    <FilterPanel
      facets={facets}
      filters={filters}
      onChange={setFilters}
      onReset={resetFilters}
      idPrefix={idPrefix}
    />
  );

  if (!query) {
    return (
      <>
        <ResultsHeader query="" />
        <main id="main" className="mx-auto max-w-[84rem] px-5 py-12">
          <StartSearchPrompt />
        </main>
      </>
    );
  }

  return (
    <>
      <ResultsHeader query={query} />

      <main
        id="main"
        // Lets tests (and anyone debugging) see the stream's state directly.
        data-search-phase={stream.phase}
        className="mx-auto max-w-[84rem] px-5 pb-20"
      >
        <div className="border-b border-border py-7">
          <p className="label-eyebrow">Your search</p>
          <h1 className="mt-2 max-w-3xl font-serif text-2xl leading-snug sm:text-3xl">
            {query}
          </h1>
          <IntentChips intent={stream.intent} parser={stream.parser} />
        </div>

        <div className="space-y-4 py-5">
          {stream.reconnecting ? <ReconnectingNotice /> : null}

          {stream.isLoading || stream.failedRetailers.length > 0 ? (
            <RetailerProgress retailers={stream.activeRetailers} isLoading={stream.isLoading} />
          ) : null}

          {settled ? (
            <PartialResultsNotice
              failedRetailers={stream.failedRetailers}
              warnings={stream.warnings}
            />
          ) : null}
        </div>

        {stream.phase === 'error' && stream.groups.length === 0 ? (
          <SearchFailure
            message={stream.error ?? 'Something went wrong.'}
            onRetry={stream.retry}
          />
        ) : (
          <div className="grid gap-8 lg:grid-cols-[15rem_minmax(0,1fr)] lg:gap-10">
            <aside className="hidden lg:block">
              <div className="sticky top-24">{renderFilterPanel('')}</div>
            </aside>

            <div className="min-w-0">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border pb-4">
                <div className="flex min-w-0 flex-wrap items-baseline gap-x-3 gap-y-1">
                  <p className="text-sm text-foreground" aria-live="polite">
                    {stream.isLoading && visibleGroups.length === 0
                      ? 'Searching…'
                      : pluralise(visibleGroups.length, 'item')}
                    {activeFilterCount > 0 && stream.groups.length !== visibleGroups.length
                      ? ` of ${stream.groups.length}`
                      : ''}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    <span className="sr-only">Results last updated </span>
                    Updated {formatRelativeTime(stream.resultsUpdatedAt)}
                  </p>
                  {stream.servedFromCache && settled ? (
                    <Badge variant="outline" className="font-normal">
                      {stream.cacheState === 'refreshed' ? 'Refreshed' : 'Cached'}
                    </Badge>
                  ) : null}
                </div>

                <div className="flex items-center gap-2">
                  <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
                    <SheetTrigger asChild>
                      <Button variant="outline" size="sm" className="lg:hidden">
                        <SlidersHorizontal aria-hidden="true" className="size-3.5" />
                        Filters
                        {activeFilterCount > 0 ? ` (${activeFilterCount})` : ''}
                      </Button>
                    </SheetTrigger>
                    <SheetContent side="bottom" className="overflow-y-auto">
                      <SheetTitle className="label-eyebrow">Filters</SheetTitle>
                      {renderFilterPanel('sheet-')}
                      <Button onClick={() => setSheetOpen(false)} className="w-full">
                        Show {pluralise(visibleGroups.length, 'item')}
                      </Button>
                    </SheetContent>
                  </Sheet>

                  <SortSelect value={sort} onChange={setChosenSort} />
                </div>
              </div>

              {noResults ? (
                <div className="pt-8">
                  <EmptyResults query={query} />
                </div>
              ) : filteredEverythingOut ? (
                <div className="pt-8">
                  <NoFilterMatches onReset={resetFilters} />
                </div>
              ) : (
                <ul
                  data-testid="product-grid"
                  className="grid grid-cols-1 gap-x-5 gap-y-8 pt-6 sm:grid-cols-2 xl:grid-cols-3"
                >
                  {visibleGroups.map((group, index) => (
                    <li key={group.group_id}>
                      <ProductCard
                        group={group}
                        position={index + 1}
                        searchId={stream.searchId}
                        className="h-full"
                      />
                    </li>
                  ))}
                  {showSkeletons
                    ? Array.from({ length: SKELETON_COUNT }).map((_, index) => (
                        <li key={`skeleton-${index}`}>
                          <ProductCardSkeleton />
                        </li>
                      ))
                    : null}
                </ul>
              )}

              {stream.isLoading && visibleGroups.length > 0 ? (
                <p
                  className="pt-8 text-center text-sm text-muted-foreground"
                  aria-live="polite"
                >
                  Still searching — more results may appear.
                </p>
              ) : null}
            </div>
          </div>
        )}
      </main>
    </>
  );
}
