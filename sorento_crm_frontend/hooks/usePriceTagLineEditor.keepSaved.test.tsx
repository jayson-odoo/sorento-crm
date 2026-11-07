/**
 * PRICETAG-COMBO-FORMAT fix round 1, R6 (hook side): when the template lookup answers for a loaded
 * line, a saved template that no longer fits the line's type is KEPT, not replaced by the type's
 * default; a line with no saved pick still gets the default; a user pick replaces it.
 *
 * Written test-FIRST: the lookup effect keeps a pick only if it fits today.
 */
import { act, renderHook, waitFor } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { emptyDraftLine, type DraftLine } from '@/lib/dealer-kit/price-tag-draft-lines';
import type { PriceMode } from '@/app/(auth)/portal/lib/price-tag-request-service';
import { usePriceTagLineEditor } from './usePriceTagLineEditor';

const opt = (id: string, price_type: string | null, defaults: { s?: boolean; l?: boolean } = {}) => ({
  id,
  name: id,
  family: 'ala_carte',
  published: true,
  width_mm: 80,
  height_mm: 50,
  price_type,
  default_list: !!defaults.l,
  default_selling: !!defaults.s,
});

function setup(initial: DraftLine[], mode: PriceMode = 'selling') {
  const lookups = {
    lookupTagItems: vi.fn(async () => []),
    lookupProductCombos: vi.fn(async () => ({ host_guarded: false, combos: [] })),
    lookupLinePricing: vi.fn(async () => []),
    lookupProductTagTemplates: vi.fn(async () => [opt('lp', 'list', { l: true }), opt('sp', 'selling', { s: true })]),
  };
  return renderHook(() => {
    const [lines, setLines] = useState(initial);
    const editor = usePriceTagLineEditor({ lines, setLines, priceMode: mode, lookups: lookups as never });
    return { lines, editor };
  });
}

const loaded = (templateId: string | null): DraftLine =>
  ({
    ...emptyDraftLine(),
    key: 'l1',
    line_type: 'product',
    product_id: 'p1',
    code: 'ZZT1',
    name: 'ZZT 1',
    price_type: 'selling',
    tag_template_id: templateId,
  }) as unknown as DraftLine;

describe('lookup keeps a saved template (R6)', () => {
  it('R6: a loaded SP line saved on an LP-only template keeps it after the lookup', async () => {
    const hook = setup([loaded('lp')]);
    await waitFor(() => expect(hook.result.current.lines[0].tag_templates_for).toBe('p1'));
    expect(hook.result.current.lines[0].tag_template_id).toBe('lp');
  });

  it('R6: a line with no saved pick still starts on the SP default', async () => {
    const hook = setup([loaded(null)]);
    await waitFor(() => expect(hook.result.current.lines[0].tag_templates_for).toBe('p1'));
    expect(hook.result.current.lines[0].tag_template_id).toBe('sp');
  });

  it('R6: a user pick replaces the kept template', async () => {
    const hook = setup([loaded('lp')]);
    await waitFor(() => expect(hook.result.current.lines[0].tag_templates_for).toBe('p1'));
    act(() => hook.result.current.editor.chooseTemplate('l1', 'sp'));
    expect(hook.result.current.lines[0].tag_template_id).toBe('sp');
  });
});
