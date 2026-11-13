/**
 * PRICETAG-ALA-CARTE AC-12 (frontend half): a saved line carries its server id in the form payload, so
 * replace_lines / portal revise can match marketing's tags by line id when a product repeats. A line
 * added in the form carries no id. AC-5: lineToDraft keeps the saved package exactly.
 *
 * Written test-FIRST against pricetag-ala-carte-acceptance-criteria.md; fake codes only.
 */
import { describe, expect, it } from 'vitest';

import { draftLinesPayload, emptyDraftLine, lineToDraft, type DraftLine } from './price-tag-draft-lines';

const savedLine = (id: string, comboId: string | null) =>
  lineToDraft({
    id,
    line_type: 'product',
    product_id: 'p-ala-1',
    product_set_id: null,
    name: 'P-ALA-1',
    code: 'P-ALA-1',
    quantity: 1,
    combo_id: comboId,
    parts: [],
  } as never);

describe('AC-12 draftLinesPayload sends the saved line id', () => {
  it('two saved lines of the same product each send their own server id', () => {
    const payload = draftLinesPayload([savedLine('srv-line-1', 'c-ala-1'), savedLine('srv-line-2', null)], 'list');
    expect(payload.map((l) => (l as { id?: string | null }).id)).toEqual(['srv-line-1', 'srv-line-2']);
    expect(payload.map((l) => l.combo_id)).toEqual(['c-ala-1', null]);
  });

  it('a line added in the form sends no id', () => {
    const added = {
      ...emptyDraftLine(),
      line_type: 'product',
      product_id: 'p-ala-1',
      code: 'P-ALA-1',
      name: 'P-ALA-1',
    } as DraftLine;
    const [line] = draftLinesPayload([added], 'list');
    expect((line as { id?: string | null }).id ?? null).toBeNull();
  });

  it('mixed: a saved line keeps its id and a new line of the same product next to it has none', () => {
    const added = { ...emptyDraftLine(), line_type: 'product', product_id: 'p-ala-1', code: 'P-ALA-1' } as DraftLine;
    const payload = draftLinesPayload([{ ...emptyDraftLine(), ...savedLine('srv-line-1', null) } as DraftLine, added], 'list');
    expect((payload[0] as { id?: string | null }).id).toBe('srv-line-1');
    expect((payload[1] as { id?: string | null }).id ?? null).toBeNull();
  });
});

describe('AC-5 lineToDraft keeps the saved package', () => {
  it('combo_id null stays null and a saved combo stays', () => {
    expect(savedLine('srv-line-1', null).combo_id).toBeNull();
    expect(savedLine('srv-line-2', 'c-ala-1').combo_id).toBe('c-ala-1');
  });
});
