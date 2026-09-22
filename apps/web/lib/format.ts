/** Display formatting helpers. Pure functions - unit tested in `tests/`. */

const currencyFormatters = new Map<string, Intl.NumberFormat>();

function formatterFor(currency: string): Intl.NumberFormat {
  const key = currency.toUpperCase();
  let formatter = currencyFormatters.get(key);
  if (!formatter) {
    formatter = new Intl.NumberFormat('en-AU', {
      style: 'currency',
      currency: key,
      currencyDisplay: 'narrowSymbol',
      maximumFractionDigits: 2,
      minimumFractionDigits: 2,
    });
    currencyFormatters.set(key, formatter);
  }
  return formatter;
}

export function formatPrice(amount: number, currency = 'AUD'): string {
  if (!Number.isFinite(amount)) return '—';
  try {
    return formatterFor(currency).format(amount);
  } catch {
    // Unknown ISO code - show the number with the code rather than failing.
    return `${currency.toUpperCase()} ${amount.toFixed(2)}`;
  }
}

/** Drops a trailing ".00" so grids of prices stay quiet. */
export function formatPriceCompact(amount: number, currency = 'AUD'): string {
  return formatPrice(amount, currency).replace(/[.,]00$/, '');
}

export function formatRelativeTime(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return 'just now';
  const timestamp = Date.parse(iso);
  if (Number.isNaN(timestamp)) return 'just now';

  const seconds = Math.max(0, Math.round((now - timestamp) / 1000));
  if (seconds < 45) return 'just now';
  if (seconds < 90) return '1 minute ago';

  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} minutes ago`;

  const hours = Math.round(minutes / 60);
  if (hours === 1) return '1 hour ago';
  if (hours < 24) return `${hours} hours ago`;

  const days = Math.round(hours / 24);
  return days === 1 ? '1 day ago' : `${days} days ago`;
}

export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return '';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export function titleCase(value: string): string {
  return value
    .split(' ')
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

export function pluralise(count: number, singular: string, plural = `${singular}s`): string {
  return `${count.toLocaleString('en-AU')} ${count === 1 ? singular : plural}`;
}
