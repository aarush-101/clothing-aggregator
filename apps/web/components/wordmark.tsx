import Link from 'next/link';

import { cn } from '@/lib/utils';

/** The text logo. Deliberately the only piece of branding in the product. */
export function Wordmark({
  className,
  size = 'default',
  withTagline = false,
}: {
  className?: string;
  size?: 'default' | 'large';
  withTagline?: boolean;
}) {
  return (
    <Link
      href="/"
      className={cn('inline-flex flex-col items-center gap-2 rounded-sm', className)}
      aria-label="Marle — go to search"
    >
      <span
        className={cn(
          'font-serif leading-none tracking-[-0.015em] text-foreground',
          size === 'large' ? 'text-[2.75rem] sm:text-[3.25rem]' : 'text-xl',
        )}
      >
        Marle
      </span>
      {withTagline ? <span className="label-eyebrow">Menswear search</span> : null}
    </Link>
  );
}
