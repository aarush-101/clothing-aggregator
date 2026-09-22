/**
 * Turns the parsed SearchIntent into the chips shown above the results, so the
 * shopper can see exactly how their sentence was interpreted.
 */

import { formatPriceCompact, titleCase } from './format';
import type { SearchIntent } from './types';

export type IntentChipKind =
  | 'category'
  | 'colour'
  | 'material'
  | 'fit'
  | 'style'
  | 'occasion'
  | 'size'
  | 'price'
  | 'brand'
  | 'excluded'
  | 'shipping'
  | 'gender'
  | 'keyword';

export interface IntentChip {
  key: string;
  label: string;
  kind: IntentChipKind;
}

function priceLabel(intent: SearchIntent): string | null {
  const { minimum_price: min, maximum_price: max, currency } = intent;
  if (min !== null && max !== null) {
    return `${formatPriceCompact(min, currency)}–${formatPriceCompact(max, currency)}`;
  }
  if (max !== null) return `Under ${formatPriceCompact(max, currency)}`;
  if (min !== null) return `Over ${formatPriceCompact(min, currency)}`;
  return null;
}

export function buildIntentChips(intent: SearchIntent | null): IntentChip[] {
  if (!intent) return [];
  const chips: IntentChip[] = [];

  const push = (kind: IntentChipKind, value: string, label?: string) => {
    chips.push({ key: `${kind}:${value}`, label: label ?? titleCase(value), kind });
  };

  for (const category of intent.product_categories) push('category', category);
  for (const colour of intent.colours) push('colour', colour);
  for (const material of intent.materials) push('material', material);
  for (const fit of intent.fits) push('fit', fit);
  for (const style of intent.styles) push('style', style);
  if (intent.occasion) push('occasion', intent.occasion);

  if (intent.size) {
    push('size', intent.size, `Size ${intent.size.toUpperCase()}`);
  }

  const price = priceLabel(intent);
  if (price) chips.push({ key: 'price', label: price, kind: 'price' });

  for (const brand of intent.brands) push('brand', brand);
  for (const brand of intent.excluded_brands) {
    chips.push({ key: `excluded:${brand}`, label: `Not ${titleCase(brand)}`, kind: 'excluded' });
  }

  const destination = intent.destination_city ?? intent.destination_country;
  if (destination) {
    chips.push({
      key: 'shipping',
      label: `Ships to ${destination}`,
      kind: 'shipping',
    });
  }

  if (intent.gender && intent.gender !== 'men') push('gender', intent.gender);

  for (const keyword of intent.additional_keywords.slice(0, 3)) push('keyword', keyword);

  return chips;
}
