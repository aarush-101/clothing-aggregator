import { describe, expect, it } from 'vitest';

import { buildIntentChips } from '@/lib/intent-chips';

import { makeIntent } from './fixtures';

function labels(intent: Parameters<typeof buildIntentChips>[0]) {
  return buildIntentChips(intent).map((chip) => chip.label);
}

describe('buildIntentChips', () => {
  it('returns nothing without an intent', () => {
    expect(buildIntentChips(null)).toEqual([]);
  });

  it('shows the interpreted attributes', () => {
    expect(labels(makeIntent())).toEqual(
      expect.arrayContaining(['Shirt', 'Black', 'Linen', 'Relaxed']),
    );
  });

  it('renders a maximum budget as "Under $X"', () => {
    expect(labels(makeIntent({ maximum_price: 120 }))).toContain('Under $120');
  });

  it('renders a minimum budget as "Over $X"', () => {
    expect(labels(makeIntent({ maximum_price: null, minimum_price: 90 }))).toContain(
      'Over $90',
    );
  });

  it('renders a price range', () => {
    const chips = labels(makeIntent({ minimum_price: 80, maximum_price: 150 }));
    expect(chips).toContain('$80–$150');
  });

  it('renders the size in upper case', () => {
    expect(labels(makeIntent({ size: 'm' }))).toContain('Size M');
  });

  it('marks excluded brands', () => {
    expect(labels(makeIntent({ excluded_brands: ['zara'] }))).toContain('Not Zara');
  });

  it('always shows the shipping destination', () => {
    expect(labels(makeIntent())).toContain('Destination: Sydney');
  });

  it('falls back to the country when no city was given', () => {
    expect(labels(makeIntent({ destination_city: null }))).toContain('Destination: AU');
  });

  it('hides the default gender and shows a non-default one', () => {
    expect(labels(makeIntent())).not.toContain('Men');
    expect(labels(makeIntent({ gender: 'unisex' }))).toContain('Unisex');
  });

  it('caps loose keywords', () => {
    const chips = buildIntentChips(
      makeIntent({ additional_keywords: ['a', 'b', 'c', 'd', 'e'] }),
    );
    expect(chips.filter((chip) => chip.kind === 'keyword')).toHaveLength(3);
  });

  it('produces unique keys', () => {
    const chips = buildIntentChips(makeIntent({ colours: ['black', 'navy'] }));
    expect(new Set(chips.map((chip) => chip.key)).size).toBe(chips.length);
  });
});
