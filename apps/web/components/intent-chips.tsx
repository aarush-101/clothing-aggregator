'use client';

import { Badge } from '@/components/ui/badge';
import { buildIntentChips } from '@/lib/intent-chips';
import type { SearchIntent } from '@/lib/types';

export function IntentChips({
  intent,
  parser,
}: {
  intent: SearchIntent | null;
  parser: string | null;
}) {
  const chips = buildIntentChips(intent);
  if (chips.length === 0) return null;

  return (
    <div className="mt-4">
      <h2 className="sr-only">How we interpreted your search</h2>
      <ul className="flex flex-wrap items-center gap-1.5" data-testid="intent-chips">
        {chips.map((chip) => (
          <li key={chip.key}>
            <Badge
              variant={chip.kind === 'excluded' ? 'outline' : 'default'}
              className="font-normal"
            >
              {chip.label}
            </Badge>
          </li>
        ))}
        {parser === 'deterministic' ? (
          <li>
            <Badge variant="outline" className="font-normal" title="Parsed without AI assistance">
              Keyword parsing
            </Badge>
          </li>
        ) : null}
      </ul>
    </div>
  );
}
