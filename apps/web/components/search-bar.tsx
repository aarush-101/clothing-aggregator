'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';
import { Search } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

const MAX_QUERY_LENGTH = 400;

export interface SearchBarProps {
  initialQuery?: string;
  size?: 'default' | 'large';
  autoFocus?: boolean;
  className?: string;
  /** Called instead of navigating, when the caller owns the query state. */
  onSubmitQuery?: (query: string) => void;
}

export function SearchBar({
  initialQuery = '',
  size = 'default',
  autoFocus = false,
  className,
  onSubmitQuery,
}: SearchBarProps) {
  const router = useRouter();
  const [value, setValue] = React.useState(initialQuery);
  const [syncedQuery, setSyncedQuery] = React.useState(initialQuery);
  const [error, setError] = React.useState<string | null>(null);
  const inputRef = React.useRef<HTMLInputElement>(null);
  const inputId = React.useId();
  const errorId = `${inputId}-error`;

  // Focused imperatively rather than with the `autoFocus` attribute: React
  // adds a client-only `caret-color` style for autofocused inputs, which
  // produces a hydration mismatch against the server-rendered markup. The
  // inline script below focuses on a full page load before scripts arrive;
  // this effect covers client-side navigations, where that script never runs.
  React.useEffect(() => {
    if (autoFocus) inputRef.current?.focus();
  }, [autoFocus]);

  // Navigating to a new results page changes `initialQuery`; adjust during
  // render rather than in an effect (https://react.dev/learn/you-might-not-need-an-effect).
  if (initialQuery !== syncedQuery) {
    setSyncedQuery(initialQuery);
    setValue(initialQuery);
  }

  const large = size === 'large';

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const query = value.trim();
    if (!query) {
      setError('Describe what you are looking for.');
      return;
    }
    if (query.length > MAX_QUERY_LENGTH) {
      setError(`Keep your search under ${MAX_QUERY_LENGTH} characters.`);
      return;
    }
    setError(null);
    if (onSubmitQuery) {
      onSubmitQuery(query);
      return;
    }
    router.push(`/search?q=${encodeURIComponent(query)}`);
  }

  return (
    <form onSubmit={handleSubmit} className={cn('w-full', className)} role="search">
      <label htmlFor={inputId} className="sr-only">
        Describe the menswear you are looking for
      </label>
      <div
        className={cn(
          'flex items-center gap-2 rounded-sm border border-border-strong bg-card transition-colors',
          'focus-within:border-foreground',
          large ? 'h-14 pr-2 pl-4 sm:h-16 sm:pr-2.5 sm:pl-5' : 'h-11 pr-1.5 pl-3',
        )}
      >
        <Search
          aria-hidden="true"
          className={cn('shrink-0 text-muted-foreground', large ? 'size-5' : 'size-4')}
        />
        <input
          ref={inputRef}
          id={inputId}
          name="q"
          type="search"
          enterKeyHint="search"
          autoComplete="off"
          autoCorrect="off"
          spellCheck={false}
          maxLength={MAX_QUERY_LENGTH}
          value={value}
          onChange={(event) => {
            setValue(event.target.value);
            if (error) setError(null);
          }}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? errorId : undefined}
          placeholder={large ? 'A relaxed black linen shirt under $120…' : 'Search menswear…'}
          className={cn(
            'min-w-0 flex-1 bg-transparent text-foreground outline-none',
            'placeholder:text-muted-foreground/70',
            large ? 'text-base sm:text-lg' : 'text-sm',
          )}
        />
        {autoFocus ? (
          // Runs while the HTML is parsed, so keystrokes made before the
          // JavaScript bundle loads land in the field instead of being lost.
          <script
            dangerouslySetInnerHTML={{
              __html: `document.getElementById(${JSON.stringify(inputId)})?.focus()`,
            }}
          />
        ) : null}
        <Button type="submit" size={large ? 'default' : 'sm'} className="shrink-0">
          Search
        </Button>
      </div>
      {error ? (
        <p id={errorId} role="alert" className="mt-2 text-sm text-destructive">
          {error}
        </p>
      ) : null}
    </form>
  );
}
