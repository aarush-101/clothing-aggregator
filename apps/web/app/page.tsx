import { ExampleSearches } from '@/components/example-searches';
import { SearchBar } from '@/components/search-bar';
import { Wordmark } from '@/components/wordmark';

/**
 * The home page is deliberately almost empty: a wordmark, one search field and
 * three examples. There is no catalogue to browse because nothing has been
 * fetched yet - retailers are only contacted once a search is submitted.
 */
export default function HomePage() {
  return (
    <div className="flex min-h-dvh flex-col">
      <main id="main" className="flex flex-1 items-center justify-center px-5 py-16">
        <div className="w-full max-w-[38rem] sm:-mt-[6vh]">
          <div className="flex justify-center">
            <Wordmark size="large" withTagline />
          </div>

          <div className="mt-10 sm:mt-12">
            <SearchBar size="large" autoFocus />
          </div>

          <ExampleSearches />
        </div>
      </main>

      <footer className="px-5 pb-8 text-center">
        <p className="text-xs text-muted-foreground/80">
          Retailers are searched when you search — nothing is pre-loaded.
        </p>
      </footer>
    </div>
  );
}
