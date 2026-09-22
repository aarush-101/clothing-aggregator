'use client';

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { SortPreference } from '@/lib/types';

const SORT_OPTIONS: { value: SortPreference; label: string }[] = [
  { value: 'relevance', label: 'Relevance' },
  { value: 'price_low_to_high', label: 'Lowest price' },
  { value: 'biggest_discount', label: 'Largest discount' },
  { value: 'newest', label: 'Newest' },
];

export function SortSelect({
  value,
  onChange,
}: {
  value: SortPreference;
  onChange: (value: SortPreference) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <label htmlFor="sort-select" className="label-eyebrow shrink-0">
        Sort
      </label>
      <Select value={value} onValueChange={(next) => onChange(next as SortPreference)}>
        <SelectTrigger id="sort-select" className="w-[10.5rem]" aria-label="Sort results">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {SORT_OPTIONS.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
