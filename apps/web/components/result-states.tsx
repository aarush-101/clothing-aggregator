'use client';

import { AlertTriangle, RefreshCw, SearchX } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { EXAMPLE_SEARCHES } from '@/lib/examples';
import type { RetailerStatus } from '@/lib/types';

function Panel({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-sm border border-dashed border-border-strong px-6 py-14 text-center">
      {children}
    </div>
  );
}

export function EmptyResults({ query }: { query: string }) {
  return (
    <Panel>
      <SearchX aria-hidden="true" className="mx-auto size-6 text-muted-foreground/60" />
      <h2 className="mt-4 font-serif text-xl">No matches for that search</h2>
      <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
        We searched every connected retailer for “{query}” and nothing came back. Try
        loosening a constraint — a wider budget, or fewer specifics.
      </p>
      <div className="mt-6 flex flex-col items-center gap-2">
        <p className="label-eyebrow">Try instead</p>
        <ul className="flex flex-col items-center gap-1.5">
          {EXAMPLE_SEARCHES.map((example) => (
            <li key={example}>
              <a
                href={`/search?q=${encodeURIComponent(example)}`}
                className="text-sm text-muted-foreground underline underline-offset-4 transition-colors hover:text-foreground"
              >
                {example}
              </a>
            </li>
          ))}
        </ul>
      </div>
    </Panel>
  );
}

export function NoFilterMatches({ onReset }: { onReset: () => void }) {
  return (
    <Panel>
      <SearchX aria-hidden="true" className="mx-auto size-6 text-muted-foreground/60" />
      <h2 className="mt-4 font-serif text-xl">No results match your filters</h2>
      <p className="mx-auto mt-2 max-w-sm text-sm text-muted-foreground">
        Your search found products, but none of them match every filter you have applied.
      </p>
      <Button variant="outline" size="sm" onClick={onReset} className="mt-6">
        Clear filters
      </Button>
    </Panel>
  );
}

export function SearchFailure({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <Panel>
      <AlertTriangle aria-hidden="true" className="mx-auto size-6 text-destructive" />
      <h2 className="mt-4 font-serif text-xl">That search could not be completed</h2>
      <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">{message}</p>
      <Button variant="outline" size="sm" onClick={onRetry} className="mt-6">
        <RefreshCw aria-hidden="true" className="size-3.5" />
        Try again
      </Button>
    </Panel>
  );
}

/**
 * Non-blocking notice: results from the retailers that did respond are shown
 * above it, so a single outage never empties the page.
 */
export function PartialResultsNotice({
  failedRetailers,
  warnings,
}: {
  failedRetailers: RetailerStatus[];
  warnings: string[];
}) {
  const notices = warnings.filter((warning) => warning.trim().length > 0);
  if (failedRetailers.length === 0 && notices.length === 0) return null;

  return (
    <div
      role="status"
      data-testid="partial-results-notice"
      className="flex items-start gap-3 rounded-sm border border-border bg-muted/60 px-4 py-3 text-sm"
    >
      <AlertTriangle
        aria-hidden="true"
        className="mt-0.5 size-4 shrink-0 text-muted-foreground"
      />
      <div className="min-w-0 space-y-1">
        {failedRetailers.length > 0 ? (
          <p className="text-foreground">
            Showing partial results —{' '}
            {failedRetailers.map((retailer) => retailer.name).join(', ')}{' '}
            {failedRetailers.length === 1 ? 'did not respond' : 'did not respond'}.
          </p>
        ) : null}
        {notices.map((warning) => (
          <p key={warning} className="text-muted-foreground">
            {warning}
          </p>
        ))}
      </div>
    </div>
  );
}

export function ReconnectingNotice() {
  return (
    <div
      role="status"
      className="flex items-center gap-2 rounded-sm border border-border bg-muted/60 px-4 py-2.5 text-sm text-muted-foreground"
    >
      <RefreshCw aria-hidden="true" className="size-3.5 animate-spin" />
      Reconnecting to the results stream…
    </div>
  );
}

export function StartSearchPrompt() {
  return (
    <Panel>
      <h2 className="font-serif text-xl">Describe what you are looking for</h2>
      <p className="mx-auto mt-2 max-w-sm text-sm text-muted-foreground">
        Use the search field above — for example, “{EXAMPLE_SEARCHES[0]}”.
      </p>
    </Panel>
  );
}
