'use client';

import { AlertCircle, Check, Loader2 } from 'lucide-react';

import { cn } from '@/lib/utils';
import { formatDuration, pluralise } from '@/lib/format';
import type { RetailerStatus } from '@/lib/types';

function StateIcon({ state }: { state: RetailerStatus['state'] }) {
  if (state === 'completed') {
    return <Check aria-hidden="true" className="size-3.5 text-positive" strokeWidth={2.5} />;
  }
  if (state === 'failed') {
    return <AlertCircle aria-hidden="true" className="size-3.5 text-destructive" />;
  }
  if (state === 'running') {
    return <Loader2 aria-hidden="true" className="size-3.5 animate-spin text-foreground" />;
  }
  return (
    <span
      aria-hidden="true"
      className="animate-pulse-dot size-1.5 rounded-full bg-muted-foreground"
    />
  );
}

function stateLabel(retailer: RetailerStatus): string {
  switch (retailer.state) {
    case 'completed':
      return retailer.product_count > 0
        ? pluralise(retailer.product_count, 'match', 'matches')
        : 'No matches';
    case 'failed':
      return retailer.error ?? 'Unavailable';
    case 'running':
      return 'Searching…';
    default:
      return 'Queued';
  }
}

export function RetailerProgress({
  retailers,
  isLoading,
}: {
  retailers: RetailerStatus[];
  isLoading: boolean;
}) {
  if (retailers.length === 0) return null;

  const done = retailers.filter((r) => r.state === 'completed' || r.state === 'failed').length;

  return (
    <section
      aria-label="Retailer progress"
      className="rounded-sm border border-border bg-card/60 p-4"
    >
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="label-eyebrow">
          {isLoading ? 'Searching retailers' : 'Retailers searched'}
        </h2>
        <span className="text-xs text-muted-foreground tabular-nums">
          {done}/{retailers.length}
        </span>
      </div>

      <ul
        className="mt-3 grid gap-x-6 gap-y-2 sm:grid-cols-2"
        aria-live="polite"
        aria-busy={isLoading}
      >
        {retailers.map((retailer) => (
          <li
            key={retailer.key}
            className="flex min-w-0 items-center justify-between gap-3 text-sm"
            data-testid={`retailer-${retailer.key}`}
            data-state={retailer.state}
          >
            <span className="flex min-w-0 items-center gap-2">
              <span className="flex size-3.5 items-center justify-center">
                <StateIcon state={retailer.state} />
              </span>
              <span
                className={cn(
                  'truncate',
                  retailer.state === 'pending' && 'text-muted-foreground',
                )}
              >
                {retailer.name}
              </span>
            </span>
            <span
              className={cn(
                'flex min-w-0 items-center gap-2 text-xs tabular-nums',
                retailer.state === 'failed' ? 'text-destructive' : 'text-muted-foreground',
              )}
              title={retailer.state === 'failed' ? (retailer.error ?? undefined) : undefined}
            >
              <span className="truncate">{stateLabel(retailer)}</span>
              {retailer.state === 'completed' && retailer.duration_ms ? (
                <span className="shrink-0 opacity-60">
                  {formatDuration(retailer.duration_ms)}
                </span>
              ) : null}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
