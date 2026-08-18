/**
 * The sales order edit session: what one Save actually sends, and what it refuses to send.
 *
 * The decisions pinned here are the ones that make an edit view safe rather than merely
 * possible: an untouched field is not in the body at all (so a save cannot blank it), an
 * untouched line set is not rewritten (the write is a REPLACE, so sending it back is a real
 * rewrite of rows nobody edited), a staged removal is simply absent from the body, and Cancel
 * puts the screen back exactly where it was.
 */
import { act } from 'react';
import { renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { StagedSalesOrderLine } from '../../../../_shared/types/projectSalesOrder.types';
import {
  salesOrderLineErrors,
  stagedLinesToBody,
  useSalesOrderEditSession,
} from './useSalesOrderEditSession';

function line(overrides: Partial<StagedSalesOrderLine> = {}): StagedSalesOrderLine {
  return {
    id: 'l1',
    key: 'l1',
    line: null,
    draft: {
      product_id: 'p1',
      description: 'CABANA S/STEEL FLOOR GRATING 6"',
      qty: '600',
      uom: 'UNIT',
      unit_price: '11.16',
      delivery_date: '2026-07-01',
      stock_location: 'BRW-BB',
    },
    removed: false,
    ...overrides,
  };
}

describe('useSalesOrderEditSession', () => {
  it('sends nothing at all until something is changed', () => {
    const { result } = renderHook(() => useSalesOrderEditSession());

    act(() => result.current.begin());
    act(() => result.current.seed([line()]));

    expect(result.current.isEditing).toBe(true);
    expect(result.current.isDirty).toBe(false);
    expect(result.current.body).toEqual({});
  });

  it('sends only the header field that was typed into', () => {
    const { result } = renderHook(() => useSalesOrderEditSession());

    act(() => result.current.begin());
    act(() => result.current.seed([line()]));
    act(() => result.current.stageHeader({ area_group: 'COMMON AREA' }));

    expect(result.current.isDirty).toBe(true);
    expect(result.current.body).toEqual({ area_group: 'COMMON AREA' });
    // The lines were never touched, so they are NOT sent: the write replaces the whole set.
    expect(result.current.body.lines).toBeUndefined();
  });

  it('clears a header field to null rather than to an empty string', () => {
    const { result } = renderHook(() => useSalesOrderEditSession({ area_group: 'TOWER' }));

    act(() => result.current.begin());
    act(() => result.current.stageHeader({ area_group: '   ' }));

    expect(result.current.isDirty).toBe(true);
    expect(result.current.body).toEqual({ area_group: null });
  });

  it('is not dirty when a header field is typed and typed back to what is stored', () => {
    const { result } = renderHook(() => useSalesOrderEditSession({ area_group: 'TOWER' }));

    act(() => result.current.begin());
    act(() => result.current.seed([line()]));
    act(() => result.current.stageHeader({ area_group: 'TOWERS' }));
    expect(result.current.isDirty).toBe(true);

    act(() => result.current.stageHeader({ area_group: 'TOWER' }));

    // Nothing to save, nothing to warn about on the way out, and no no-op PUT.
    expect(result.current.isDirty).toBe(false);
    expect(result.current.body).toEqual({});
  });

  it('treats a blank stored value and an erased field as the same thing', () => {
    const { result } = renderHook(() => useSalesOrderEditSession({ area_group: null }));

    act(() => result.current.begin());
    act(() => result.current.stageHeader({ area_group: 'PODIUM' }));
    act(() => result.current.stageHeader({ area_group: '' }));

    expect(result.current.isDirty).toBe(false);
    expect(result.current.body).toEqual({});
  });

  it('measures the header against the stored values as they load, not as they were on mount', () => {
    const { result, rerender } = renderHook(
      ({ stored }: { stored?: { area_group?: string | null } }) => useSalesOrderEditSession(stored),
      { initialProps: { stored: undefined } as { stored?: { area_group?: string | null } } },
    );

    act(() => result.current.begin());
    act(() => result.current.stageHeader({ area_group: 'TOWER' }));
    expect(result.current.isDirty).toBe(true);

    rerender({ stored: { area_group: 'TOWER' } });

    expect(result.current.isDirty).toBe(false);
  });

  it('sends the whole line set once any line moves', () => {
    const { result } = renderHook(() => useSalesOrderEditSession());

    act(() => result.current.begin());
    act(() => result.current.seed([line(), line({ id: 'l2', key: 'l2' })]));
    act(() =>
      result.current.stage([
        line({ draft: { ...line().draft, qty: '601' } }),
        line({ id: 'l2', key: 'l2' }),
      ]),
    );

    expect(result.current.isDirty).toBe(true);
    expect(result.current.body.lines).toHaveLength(2);
    expect(result.current.body.lines?.[0]).toMatchObject({ id: 'l1', qty: '601' });
    expect(result.current.body.lines?.[1]).toMatchObject({ id: 'l2' });
  });

  it('leaves a removed line out of the body and counts it for the confirmation', () => {
    const { result } = renderHook(() => useSalesOrderEditSession());

    act(() => result.current.begin());
    act(() => result.current.seed([line(), line({ id: 'l2', key: 'l2' })]));
    act(() => result.current.toggleRemoved('l2'));

    expect(result.current.removedCount).toBe(1);
    expect(result.current.body.lines).toHaveLength(1);
    expect(result.current.body.lines?.[0]).toMatchObject({ id: 'l1' });
  });

  it('does not count a never-saved row as a deletion', () => {
    const { result } = renderHook(() => useSalesOrderEditSession());

    act(() => result.current.begin());
    act(() => result.current.seed([line()]));
    act(() => result.current.stage([line(), line({ id: null, key: 'new:1' })]));
    act(() => result.current.toggleRemoved('new:1'));

    // Nothing stored is being destroyed, so Save asks nothing.
    expect(result.current.removedCount).toBe(0);
  });

  it('sends a line added in the session without an id', () => {
    const { result } = renderHook(() => useSalesOrderEditSession());

    act(() => result.current.begin());
    act(() => result.current.seed([line()]));
    act(() => result.current.stage([line(), line({ id: null, key: 'new:1' })]));

    expect(result.current.body.lines?.[1]).not.toHaveProperty('id');
  });

  it('counts the lines that are not ready to be written', () => {
    const { result } = renderHook(() => useSalesOrderEditSession());

    act(() => result.current.begin());
    act(() => result.current.seed([line()]));
    act(() =>
      result.current.stage([
        line({
          id: null,
          key: 'new:1',
          draft: { product_id: '', description: '', qty: '1', unit_price: '0' },
        }),
      ]),
    );

    expect(result.current.unfinishedCount).toBe(1);
  });

  it('Cancel throws everything away and leaves edit mode', () => {
    const { result } = renderHook(() => useSalesOrderEditSession());

    act(() => result.current.begin());
    act(() => result.current.seed([line()]));
    act(() => result.current.stageHeader({ area_group: 'PODIUM' }));
    act(() => result.current.cancel());

    expect(result.current.isEditing).toBe(false);
    expect(result.current.staged).toBeNull();
    expect(result.current.isDirty).toBe(false);
    expect(result.current.body).toEqual({});
  });

  it('seeds once, so a refetch mid-edit cannot overwrite what is being typed', () => {
    const { result } = renderHook(() => useSalesOrderEditSession());

    act(() => result.current.begin());
    act(() => result.current.seed([line()]));
    act(() => result.current.stage([line({ draft: { ...line().draft, qty: '999' } })]));
    act(() => result.current.seed([line()]));

    expect(result.current.staged?.[0].draft.qty).toBe('999');
  });
});

describe('salesOrderLineErrors', () => {
  it('accepts a line with a product and a quantity', () => {
    expect(salesOrderLineErrors({ product_id: 'p1', description: '', qty: '5' })).toEqual({});
  });

  it('wants something to call an off-catalog line', () => {
    expect(
      salesOrderLineErrors({ product_id: '', description: '  ', qty: '5' }),
    ).toHaveProperty('description');
  });

  it('refuses a quantity of zero, which orders nothing', () => {
    expect(salesOrderLineErrors({ product_id: 'p1', qty: '0' })).toHaveProperty('qty');
  });

  it('refuses a delivery date that is not an ISO day', () => {
    expect(
      salesOrderLineErrors({ product_id: 'p1', qty: '1', delivery_date: '01/07/2026' }),
    ).toHaveProperty('delivery_date');
  });
});

describe('stagedLinesToBody', () => {
  it('keeps money and quantity as the strings they arrived as', () => {
    const [body] = stagedLinesToBody([
      line({ draft: { ...line().draft, unit_price: '392.85000', qty: '927' } }),
    ]);

    expect(body.unit_price).toBe('392.85000');
    expect(body.qty).toBe('927');
    // `amount` is never sent: it is always qty x unit price, and a third number is how a line
    // comes to fail our own arithmetic check.
    expect(body).not.toHaveProperty('amount');
  });

  it('turns an empty optional cell into null rather than an empty string', () => {
    const [body] = stagedLinesToBody([
      line({
        draft: { product_id: 'p1', description: 'x', qty: '1', unit_price: '1', uom: '' },
      }),
    ]);

    expect(body.uom).toBeNull();
    expect(body.delivery_date).toBeNull();
    expect(body.stock_location).toBeNull();
  });
});
