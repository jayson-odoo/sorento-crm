/**
 * PRICETAG-LPSP S6 (AC-19): the draft line carries its own LP/SP.
 *
 * Written test-FIRST (PRINCIPLES.md Phase 2). `DraftLine.price_type` does not exist: a saved line's
 * type is dropped on reopen and never sent. `price_type` null/absent means "take the header
 * default"; the server stores the request's mode for such a line.
 */
import { describe, expect, it } from 'vitest';

import {
  draftLinesPayload,
  emptyDraftLine,
  lineToDraft,
  type DraftLine,
  type DraftLineSource,
} from './price-tag-draft-lines';

const source = (patch: Record<string, unknown> = {}): DraftLineSource =>
  ({
    id: 'line-1',
    line_type: 'product',
    product_id: 'p1',
    product_set_id: null,
    name: 'Sink',
    code: 'SK-1',
    quantity: 1,
    ...patch,
  }) as DraftLineSource;

const draft = (patch: Partial<DraftLine> & Record<string, unknown> = {}): DraftLine =>
  ({ ...emptyDraftLine(), key: 'l1', product_id: 'p1', code: 'SK-1', ...patch }) as DraftLine;

describe('lineToDraft price_type (AC-19)', () => {
  it('reads the saved line type back', () => {
    expect((lineToDraft(source({ price_type: 'selling' })) as never as Record<string, unknown>).price_type).toBe('selling');
    expect((lineToDraft(source({ price_type: 'list' })) as never as Record<string, unknown>).price_type).toBe('list');
  });

  it('a saved line without a type stays untyped, it is not forced to a mode', () => {
    const value = (lineToDraft(source()) as never as Record<string, unknown>).price_type;
    expect(value == null).toBe(true);
  });
});

describe('draftLinesPayload price_type (AC-19)', () => {
  const payloadOf = (line: DraftLine) =>
    draftLinesPayload([line])[0] as unknown as Record<string, unknown>;

  it('sends each line its own type', () => {
    const lines = [
      draft({ key: 'a', price_type: 'list' } as never),
      draft({ key: 'b', price_type: 'selling' } as never),
    ];
    const out = draftLinesPayload(lines) as unknown as Array<Record<string, unknown>>;
    expect(out.map((l) => l.price_type)).toEqual(['list', 'selling']);
  });

  it('sends a typed SP on an SP line', () => {
    const out = payloadOf(draft({ price_type: 'selling', manual_sell_price: 599 } as never));
    expect(out.manual_sell_price).toBe(599);
  });

  it('never sends a typed price on an LP line (the server refuses it)', () => {
    const out = payloadOf(draft({ price_type: 'list', manual_sell_price: 599 } as never));
    expect(out.manual_sell_price == null).toBe(true);
  });

  it('never sends a typed price together with a promotion', () => {
    const out = payloadOf(
      draft({ price_type: 'selling', promotion_id: 'promo-1', manual_sell_price: 599 } as never),
    );
    expect(out.promotion_id).toBe('promo-1');
    expect(out.manual_sell_price == null).toBe(true);
  });
});
