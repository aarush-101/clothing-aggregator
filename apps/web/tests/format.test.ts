import { describe, expect, it } from 'vitest';

import {
  formatDuration,
  formatPrice,
  formatPriceCompact,
  formatRelativeTime,
  pluralise,
  titleCase,
} from '@/lib/format';

describe('formatPrice', () => {
  it('formats AUD with a narrow symbol', () => {
    expect(formatPrice(119, 'AUD')).toBe('$119.00');
  });

  it('handles other currencies', () => {
    expect(formatPrice(119, 'GBP')).toContain('119.00');
  });

  it('renders an unrecognised but well-formed code alongside the amount', () => {
    // Intl accepts any three-letter code and renders it literally.
    expect(formatPrice(119, 'XYZ')).toMatch(/XYZ\s119\.00/);
  });

  it('falls back when Intl rejects the currency code', () => {
    expect(formatPrice(119, 'not-a-code')).toBe('NOT-A-CODE 119.00');
  });

  it('handles non-finite input without throwing', () => {
    expect(formatPrice(Number.NaN)).toBe('—');
  });
});

describe('formatPriceCompact', () => {
  it('drops trailing zero cents', () => {
    expect(formatPriceCompact(119, 'AUD')).toBe('$119');
  });

  it('keeps meaningful cents', () => {
    expect(formatPriceCompact(119.95, 'AUD')).toBe('$119.95');
  });
});

describe('formatRelativeTime', () => {
  const now = Date.parse('2026-09-22T12:00:00Z');

  it.each([
    ['2026-09-22T11:59:50Z', 'just now'],
    ['2026-09-22T11:58:00Z', '2 minutes ago'],
    ['2026-09-22T11:00:00Z', '1 hour ago'],
    ['2026-09-22T07:00:00Z', '5 hours ago'],
    ['2026-09-21T12:00:00Z', '1 day ago'],
    ['2026-09-19T12:00:00Z', '3 days ago'],
  ])('renders %s as %s', (iso, expected) => {
    expect(formatRelativeTime(iso, now)).toBe(expected);
  });

  it('handles missing and invalid timestamps', () => {
    expect(formatRelativeTime(null, now)).toBe('just now');
    expect(formatRelativeTime('nonsense', now)).toBe('just now');
  });
});

describe('misc formatters', () => {
  it('formats durations', () => {
    expect(formatDuration(420)).toBe('420ms');
    expect(formatDuration(1500)).toBe('1.5s');
    expect(formatDuration(null)).toBe('');
  });

  it('pluralises', () => {
    expect(pluralise(1, 'item')).toBe('1 item');
    expect(pluralise(3, 'item')).toBe('3 items');
    expect(pluralise(2, 'match', 'matches')).toBe('2 matches');
  });

  it('title-cases', () => {
    expect(titleCase('smart casual')).toBe('Smart Casual');
  });
});
