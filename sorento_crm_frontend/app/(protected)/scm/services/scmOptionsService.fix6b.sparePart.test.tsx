/**
 * SPARE-PART-ORDER-REQUEST fix round 6, E2 (owner label rule, `lib/product-display.ts`
 * codeWithName: the name only when it differs from the code). `searchProductOptions` gains an
 * optional separator argument (after `valueKey`) whose DEFAULT stays ' · ', so every existing
 * caller (sales order form, reorder plan header, run planning modal, scheduled task scope) keeps
 * its labels; the spare part request form passes ' - '.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiFetch = vi.fn(
  async () =>
    new Response(
      JSON.stringify({
        data: [
          { id: 'p1', product_code: 'JC-PUMP', product_name: 'JC-PUMP' },
          { id: 'p2', product_code: 'SP-SEAL', product_name: 'Pump seal' },
        ],
      }),
      { status: 200, headers: { 'content-type': 'application/json' } },
    ),
);
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...(a as [])) }));

import { searchProductOptions } from './scmOptionsService';

type Search = (q: string, page?: number, valueKey?: 'product_code' | 'id', sep?: string) => Promise<{ value: string; label: string }[]>;
const search = searchProductOptions as unknown as Search;

beforeEach(() => vi.clearAllMocks());

describe('E2: searchProductOptions separator', () => {
  it('the default stays " · " for existing callers, and a code-only product reads its code once', async () => {
    const options = await search('', 0);
    expect(options.map((o) => o.label)).toEqual(['JC-PUMP', 'SP-SEAL · Pump seal']);
  });

  it('a caller passing " - " gets the owner-rule label, values by id', async () => {
    const options = await search('', 0, 'id', ' - ');
    expect(options).toEqual([
      expect.objectContaining({ value: 'p1', label: 'JC-PUMP' }),
      expect.objectContaining({ value: 'p2', label: 'SP-SEAL - Pump seal' }),
    ]);
  });
});
