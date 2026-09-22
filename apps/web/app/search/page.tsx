import { Suspense } from 'react';
import type { Metadata } from 'next';

import { SearchResultsView } from '@/components/search-results-view';

export const metadata: Metadata = {
  title: 'Search results',
  // Result pages are generated per query and have no lasting value to index.
  robots: { index: false, follow: true },
};

export default function SearchPage() {
  return (
    <Suspense fallback={<SearchPageFallback />}>
      <SearchResultsView />
    </Suspense>
  );
}

function SearchPageFallback() {
  return (
    <div className="mx-auto max-w-[84rem] px-5 py-16">
      <div className="animate-shimmer h-8 w-64 rounded-sm bg-muted" />
      <div className="animate-shimmer mt-4 h-4 w-40 rounded-sm bg-muted" />
    </div>
  );
}
