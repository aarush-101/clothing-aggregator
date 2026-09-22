'use client';

import * as React from 'react';
import { Shirt } from 'lucide-react';

import { cn } from '@/lib/utils';

/**
 * Plain <img> rather than next/image: retailer imagery comes from arbitrary
 * hosts that cannot all be allow-listed ahead of time, and the optimiser would
 * need network access at request time. Failures degrade to a neutral panel.
 */
export function ProductImage({
  src,
  alt,
  className,
}: {
  src: string | null;
  alt: string;
  className?: string;
}) {
  const [failed, setFailed] = React.useState(false);
  const [loaded, setLoaded] = React.useState(false);

  const showPlaceholder = !src || failed;

  return (
    <div
      className={cn(
        'relative aspect-[4/5] w-full overflow-hidden rounded-sm bg-muted',
        className,
      )}
    >
      {showPlaceholder ? (
        <div className="flex h-full w-full items-center justify-center">
          <Shirt aria-hidden="true" className="size-8 text-muted-foreground/40" />
          <span className="sr-only">No image available</span>
        </div>
      ) : (
        // eslint-disable-next-line @next/next/no-img-element -- see the note above
        <img
          src={src}
          alt={alt}
          loading="lazy"
          decoding="async"
          referrerPolicy="no-referrer"
          onLoad={() => setLoaded(true)}
          onError={() => setFailed(true)}
          className={cn(
            'h-full w-full object-cover transition-opacity duration-500',
            loaded ? 'opacity-100' : 'opacity-0',
          )}
        />
      )}
    </div>
  );
}
