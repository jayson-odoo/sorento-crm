/**
 * PRICETAG-UPGRADE-VARIANTS FE test 9 (data half, AC-F2c): the draft line carries
 * `excluded_variant_ids` (the UNTICKED members) through reopen and into the create / update / revise
 * payload. Written test-FIRST.
 */
import { describe, expect, it } from 'vitest';

import { draftLinesPayload, emptyDraftLine, lineToDraft, type DraftLine, type DraftLineSource } from './price-tag-draft-lines';

const source = (patch: Record<string, unknown> = {}): DraftLineSource =>
  ({
    id: 'line-1', line_type: 'product', product_id: 'p1', product_set_id: null,
    name: 'WC', code: 'SRTWC8354-SH', quantity: 1, ...patch,
  }) as DraftLineSource;

const draft = (patch: Record<string, unknown> = {}): DraftLine =>
  ({ ...emptyDraftLine(), key: 'l1', product_id: 'p1', code: 'SRTWC8354-SH', quantity: 1, ...patch }) as DraftLine;

describe('excluded_variant_ids on the draft line', () => {
  it('a new line has none unticked', () => {
    expect((emptyDraftLine() as never as Record<string, unknown>).excluded_variant_ids ?? []).toEqual([]);
  });

  it('reopening a saved line reads the unticked ids back', () => {
    const line = lineToDraft(source({ excluded_variant_ids: ['v1', 'v2'] })) as never as Record<string, unknown>;
    expect(line.excluded_variant_ids).toEqual(['v1', 'v2']);
  });

  it('a saved line with none reads an empty list', () => {
    const line = lineToDraft(source()) as never as Record<string, unknown>;
    expect(line.excluded_variant_ids).toEqual([]);
  });

  it('the payload sends the unticked ids for a product line', () => {
    const [row] = draftLinesPayload([draft({ excluded_variant_ids: ['v1'] })]) as unknown as Record<string, unknown>[];
    expect(row.excluded_variant_ids).toEqual(['v1']);
  });

  it('the payload sends [] when nothing is unticked', () => {
    const [row] = draftLinesPayload([draft()]) as unknown as Record<string, unknown>[];
    expect(row.excluded_variant_ids).toEqual([]);
  });

  it('a product set line sends none', () => {
    const [row] = draftLinesPayload([
      draft({ line_type: 'product_set', product_id: null, product_set_id: 's1', excluded_variant_ids: ['v1'] }),
    ]) as unknown as Record<string, unknown>[];
    expect(row.excluded_variant_ids).toEqual([]);
  });
});
