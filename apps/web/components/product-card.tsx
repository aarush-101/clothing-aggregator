'use client';

import * as React from 'react';
import { ArrowUpRight } from 'lucide-react';

import { ProductImage } from '@/components/product-image';
import { FavouriteButton } from '@/components/favourite-button';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { recordClick } from '@/lib/api';
import { formatPriceCompact, formatRelativeTime, pluralise } from '@/lib/format';
import type { Product, ProductGroup } from '@/lib/types';
import { cn } from '@/lib/utils';

export function ProductCard({
  group,
  position,
  searchId,
  className,
}: {
  group: ProductGroup;
  position: number;
  searchId: string | null;
  className?: string;
}) {
  const product = group.primary;
  const retailerName = product.retailer_name ?? product.retailer;
  const hasDiscount = (product.discount_percent ?? 0) > 0;
  const otherOffers = group.offer_count - 1;
  const titleId = `product-${group.group_id}-title`;
  // Colourways of one garment are separate cards; name the colour unless the title does.
  const colourway = product.colours.some((colour) =>
    product.title.toLowerCase().includes(colour.toLowerCase()),
  )
    ? null
    : product.colours.slice(0, 3).join(' / ');

  // One listing per other retailer: the cheapest offer each one has for this garment.
  const alternatives = React.useMemo(() => {
    const seen = new Set([product.retailer]);
    return group.offers.filter((offer) => {
      if (seen.has(offer.retailer)) return false;
      seen.add(offer.retailer);
      return true;
    });
  }, [group.offers, product.retailer]);

  const recordOutbound = React.useCallback(
    (offer: Product) => {
      recordClick({
        retailer: offer.retailer,
        product_id: offer.product_id,
        destination_url: offer.affiliate_url,
        search_id: searchId ?? undefined,
        price: offer.price,
        currency: offer.currency,
        position,
      });
    },
    [searchId, position],
  );
  const handleOutboundClick = React.useCallback(
    () => recordOutbound(product),
    [recordOutbound, product],
  );

  return (
    <article
      aria-labelledby={titleId}
      data-testid="product-card"
      data-group-id={group.group_id}
      data-total-price={group.lowest_total_price}
      className={cn(
        'animate-rise group flex flex-col rounded-sm border border-border bg-card',
        'transition-colors hover:border-border-strong',
        className,
      )}
    >
      <div className="relative">
        <ProductImage src={product.image_url} alt={product.title} className="rounded-b-none" />

        <div className="absolute top-2.5 left-2.5 flex flex-col items-start gap-1.5">
          {hasDiscount ? (
            <Badge variant="solid" className="tabular-nums">
              {product.discount_percent}% off
            </Badge>
          ) : null}
          {product.in_stock === false ? <Badge variant="outline">Out of stock</Badge> : null}
          {product.freshness === 'stale' ? (
            <Badge variant="outline">Needs refresh</Badge>
          ) : null}
          {product.in_stock === null ? (
            <Badge variant="outline">Stock unconfirmed</Badge>
          ) : null}
        </div>

        <div className="absolute top-2 right-2">
          <FavouriteButton product={product} groupId={group.group_id} />
        </div>
      </div>

      <div className="flex flex-1 flex-col gap-3 p-4">
        <div className="space-y-1">
          {product.brand ? <p className="label-eyebrow">{product.brand}</p> : null}
          <h3 id={titleId} className="font-serif text-[1.0625rem] leading-snug text-foreground">
            {product.title}
          </h3>
          {colourway ? (
            <p
              className="text-xs text-muted-foreground capitalize"
              data-testid="product-colour"
            >
              {colourway}
            </p>
          ) : null}
        </div>

        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
          <span className="text-base font-medium tabular-nums" data-testid="product-price">
            {formatPriceCompact(product.price, product.currency)}
          </span>
          {hasDiscount && product.original_price ? (
            <span className="text-sm text-muted-foreground line-through tabular-nums">
              {formatPriceCompact(product.original_price, product.currency)}
            </span>
          ) : null}
          <span className="text-xs text-muted-foreground">
            {product.shipping_cost === 0
              ? 'Free shipping'
              : product.shipping_cost
                ? `+ ${formatPriceCompact(product.shipping_cost, product.currency)} shipping`
                : 'Shipping calculated by retailer'}
          </span>
        </div>

        {group.match_reasons.length > 0 ? (
          <p className="text-[0.8125rem] leading-relaxed text-muted-foreground">
            {group.match_reasons[0]}
          </p>
        ) : null}

        {product.available_sizes.length > 0 ? (
          <p className="text-xs text-muted-foreground">
            <span className="sr-only">Available sizes: </span>
            {product.available_sizes
              .slice(0, 8)
              .map((size) => size.toUpperCase())
              .join(' · ')}
          </p>
        ) : null}

        <div className="mt-auto space-y-3 pt-1">
          {otherOffers > 0 && alternatives.length > 0 ? (
            <div className="space-y-1.5" data-testid="other-offers">
              <p className="text-xs text-muted-foreground">
                Lowest of {pluralise(alternatives.length + 1, 'retailer')}
              </p>
              <ul className="divide-y divide-border border-y border-border">
                {alternatives.slice(0, 3).map((offer) => (
                  <li key={`${offer.retailer}-${offer.product_id}`}>
                    <a
                      href={offer.affiliate_url}
                      target="_blank"
                      rel="noopener noreferrer nofollow sponsored"
                      onClick={() => recordOutbound(offer)}
                      className="flex items-center justify-between gap-3 py-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
                    >
                      <span className="min-w-0 truncate">
                        {offer.retailer_name ?? offer.retailer}
                      </span>
                      <span className="shrink-0 tabular-nums">
                        {formatPriceCompact(offer.price, offer.currency)}
                        <ArrowUpRight aria-hidden="true" className="ml-1 inline size-3" />
                      </span>
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          <div className="flex items-center justify-between gap-3">
            <span className="min-w-0 truncate text-xs text-muted-foreground">
              {retailerName}
            </span>
            <span className="shrink-0 text-[0.6875rem] text-muted-foreground/70">
              Checked {formatRelativeTime(product.retrieved_at)}
            </span>
          </div>

          <Button asChild variant="outline" size="sm" className="w-full">
            <a
              href={product.affiliate_url}
              target="_blank"
              rel="noopener noreferrer nofollow sponsored"
              onClick={handleOutboundClick}
              data-testid="view-at-retailer"
            >
              View at {retailerName}
              <ArrowUpRight aria-hidden="true" className="size-3.5" />
            </a>
          </Button>
        </div>
      </div>
    </article>
  );
}

export function ProductCardSkeleton() {
  return (
    <div className="flex flex-col rounded-sm border border-border bg-card" aria-hidden="true">
      <div className="animate-shimmer aspect-[4/5] w-full rounded-t-sm bg-muted" />
      <div className="space-y-3 p-4">
        <div className="animate-shimmer h-2.5 w-20 rounded-sm bg-muted" />
        <div className="animate-shimmer h-4 w-4/5 rounded-sm bg-muted" />
        <div className="animate-shimmer h-4 w-16 rounded-sm bg-muted" />
        <div className="animate-shimmer h-8 w-full rounded-sm bg-muted" />
      </div>
    </div>
  );
}
