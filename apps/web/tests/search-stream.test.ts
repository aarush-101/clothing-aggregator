import { describe, expect, it } from 'vitest';

import { mergeGroups } from '@/lib/use-search-stream';

import { makeGroup, makeProduct } from './fixtures';

describe('mergeGroups', () => {
  it('returns the existing list when nothing arrives', () => {
    const existing = [makeGroup({ group_id: 'a' })];
    expect(mergeGroups(existing, [])).toBe(existing);
  });

  it('appends groups from a newly responding retailer', () => {
    const first = makeGroup({ group_id: 'a', match_score: 0.9 });
    const second = makeGroup({ group_id: 'b', match_score: 0.8 }, { product_id: 'b' });
    expect(mergeGroups([first], [second]).map((g) => g.group_id)).toEqual(['a', 'b']);
  });

  it('replaces a group when a later retailer adds an offer to it', () => {
    const initial = makeGroup({ group_id: 'a', offer_count: 1 });
    const updated = makeGroup({
      group_id: 'a',
      offer_count: 2,
      offers: [makeProduct({ product_id: '1' }), makeProduct({ product_id: '2' })],
    });
    const merged = mergeGroups([initial], [updated]);
    expect(merged).toHaveLength(1);
    expect(merged[0]!.offer_count).toBe(2);
  });

  it('keeps the list ordered by score, then price', () => {
    const low = makeGroup({ group_id: 'low', match_score: 0.4 });
    const high = makeGroup({ group_id: 'high', match_score: 0.95 }, { product_id: 'h' });
    expect(mergeGroups([low], [high]).map((g) => g.group_id)).toEqual(['high', 'low']);
  });

  it('breaks score ties with the cheaper option', () => {
    const dear = makeGroup({ group_id: 'dear', match_score: 0.8, lowest_total_price: 200 });
    const cheap = makeGroup({ group_id: 'cheap', match_score: 0.8, lowest_total_price: 100 });
    expect(mergeGroups([dear], [cheap]).map((g) => g.group_id)).toEqual(['cheap', 'dear']);
  });
});
