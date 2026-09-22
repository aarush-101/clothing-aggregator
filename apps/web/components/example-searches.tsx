'use client';

import { useRouter } from 'next/navigation';
import { ArrowUpRight } from 'lucide-react';

import { EXAMPLE_SEARCHES } from '@/lib/examples';

export function ExampleSearches() {
  const router = useRouter();

  return (
    <div className="mt-8">
      <h2 className="sr-only">Example searches</h2>
      <ul className="flex flex-col items-start gap-1.5 sm:items-center">
        {EXAMPLE_SEARCHES.map((example) => (
          <li key={example} className="max-w-full">
            <button
              type="button"
              onClick={() => router.push(`/search?q=${encodeURIComponent(example)}`)}
              className="group inline-flex max-w-full items-center gap-1.5 rounded-sm py-1 text-left text-[0.8125rem] text-muted-foreground transition-colors hover:text-foreground"
            >
              <span className="truncate">{example}</span>
              <ArrowUpRight
                aria-hidden="true"
                className="size-3.5 shrink-0 opacity-0 transition-opacity group-hover:opacity-60 group-focus-visible:opacity-60"
              />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
