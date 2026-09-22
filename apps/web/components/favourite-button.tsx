'use client';

import { Heart } from 'lucide-react';

import { useAccount } from '@/components/account-provider';
import type { Product } from '@/lib/types';
import { cn } from '@/lib/utils';

export function FavouriteButton({
  product,
  groupId,
}: {
  product: Product;
  groupId: string | null;
}) {
  const { isFavourite, toggleFavourite, available } = useAccount();
  if (!available) return null;

  const saved = isFavourite(product.retailer, product.product_id);

  return (
    <button
      type="button"
      onClick={() => toggleFavourite(product, groupId)}
      aria-pressed={saved}
      aria-label={saved ? `Remove ${product.title} from favourites` : `Save ${product.title}`}
      className={cn(
        'flex size-8 items-center justify-center rounded-full border border-border bg-card/90 backdrop-blur-sm transition-colors',
        'hover:border-border-strong',
        saved ? 'text-destructive' : 'text-muted-foreground',
      )}
    >
      <Heart className="size-4" fill={saved ? 'currentColor' : 'none'} aria-hidden="true" />
    </button>
  );
}
