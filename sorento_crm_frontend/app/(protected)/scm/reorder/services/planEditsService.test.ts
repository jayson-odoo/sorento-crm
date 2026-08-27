/**
 * planEditsService - the three reads/writes the revamp adds (plan section 4.5/4.6, UAC E1,
 * F5, F6): the bulk save PUT, the SPO history read (site pool only, R15) and the PO-history
 * read narrowed to a pool via `purchase-trend`'s `warehouse` filter, field-remapped from the
 * wire's `order_date`/`expected_date` to the dialog's `issued_at`/`eta`.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

import { getPoHistoryToPool, getSpoHistory, savePlanEdits, type PlanEditRow } from './planEditsService';

function ok(body: unknown) {
  return {
    ok: true,
    status: 200,
    headers: { get: () => 'application/json' },
    json: async () => body,
  } as unknown as Response;
}

function fail(detail: string, status = 400) {
  return {
    ok: false,
    status,
    headers: { get: () => 'application/json' },
    json: async () => ({ detail }),
    text: async () => JSON.stringify({ detail }),
  } as unknown as Response;
}

function calledUrl(): URL {
  const calls = apiFetch.mock.calls;
  return new URL(String(calls[calls.length - 1][0]), 'http://x');
}
function lastInit(): RequestInit {
  const calls = apiFetch.mock.calls;
  return (calls[calls.length - 1][1] ?? {}) as RequestInit;
}

beforeEach(() => apiFetch.mockReset());

describe('savePlanEdits (E1) - the bulk PUT', () => {
  it('PUTs /reorder-runs/{run}/plan-edits with the rows in the body', async () => {
    apiFetch.mockResolvedValue(ok({ saved_rows: 2, saved_products: 1 }));
    const rows: PlanEditRow[] = [
      { rec_id: 'r1', moq: 40 },
      { rec_id: 'r2', moq: 40 },
    ];

    const result = await savePlanEdits('run-1', rows);

    expect(calledUrl().pathname).toBe('/api/v1/scm/reorder-runs/run-1/plan-edits');
    expect(lastInit().method).toBe('PUT');
    expect(JSON.parse(String(lastInit().body))).toEqual({ rows });
    expect(result).toEqual({ saved_rows: 2, saved_products: 1 });
  });

  it('refuses to call the backend with no run to save against', async () => {
    await expect(savePlanEdits('', [])).rejects.toThrow('No plan to save against.');
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it('a non-ok response is surfaced through extractApiError', async () => {
    apiFetch.mockResolvedValue(fail('Legacy run.', 409));
    await expect(savePlanEdits('run-1', [{ rec_id: 'r1' }])).rejects.toThrow('Legacy run.');
  });
});

describe('getSpoHistory (F5) - shipping orders to the site pool', () => {
  it('GETs the run-scoped spo-history endpoint with product_id', async () => {
    apiFetch.mockResolvedValue(
      ok({
        open: [{ spo_number: 'SPO-1', supplier_name: 'Acme', qty: 10, received_qty: 0, eta: null, arrived_at: null, status: 'open' }],
        history: [],
      }),
    );

    const result = await getSpoHistory('run-1', 'p1');

    expect(calledUrl().pathname).toBe('/api/v1/scm/reorder-runs/run-1/spo-history');
    expect(calledUrl().searchParams.get('product_id')).toBe('p1');
    expect(result.open).toHaveLength(1);
    expect(result.history).toEqual([]);
  });

  it('returns empty lists rather than calling the backend with nothing to ask for', async () => {
    const result = await getSpoHistory('', '');
    expect(result).toEqual({ open: [], history: [] });
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it('a non-ok response is surfaced through extractApiError', async () => {
    apiFetch.mockResolvedValue(fail('Server error.', 500));
    await expect(getSpoHistory('run-1', 'p1')).rejects.toThrow('Server error.');
  });

  it('a body missing open/history still returns empty arrays, not undefined', async () => {
    apiFetch.mockResolvedValue(ok({}));
    const result = await getSpoHistory('run-1', 'p1');
    expect(result).toEqual({ open: [], history: [] });
  });
});

describe('getPoHistoryToPool (F6) - purchase-trend narrowed to one destination', () => {
  it('reads purchase-trend?warehouse= and remaps order_date/expected_date -> issued_at/eta', async () => {
    apiFetch.mockResolvedValue(
      ok({
        products: {
          p1: {
            lines: [
              {
                po_number: 'PO-100',
                supplier_name: 'Acme',
                qty: 50,
                unit_cost: 12.5,
                currency: 'MYR',
                order_date: '2026-08-01',
                expected_date: '2026-08-20',
                status: 'open',
              },
            ],
          },
        },
      }),
    );

    const result = await getPoHistoryToPool('run-1', 'p1', 'BRW');

    expect(calledUrl().pathname).toBe('/api/v1/scm/reorder-runs/run-1/purchase-trend');
    expect(calledUrl().searchParams.get('warehouse')).toBe('BRW');
    expect(result.history).toEqual([
      {
        po_number: 'PO-100',
        supplier_name: 'Acme',
        qty: 50,
        unit_cost: 12.5,
        currency: 'MYR',
        issued_at: '2026-08-01',
        eta: '2026-08-20',
        status: 'open',
      },
    ]);
  });

  it('returns no history when the row names no pool at all - never guesses a destination', async () => {
    const result = await getPoHistoryToPool('run-1', 'p1', null);
    expect(result).toEqual({ history: [] });
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it('a product absent from the response reads as no history, not an error', async () => {
    apiFetch.mockResolvedValue(ok({ products: {} }));
    const result = await getPoHistoryToPool('run-1', 'p1', 'BRW');
    expect(result).toEqual({ history: [] });
  });

  it('a null status reads as an empty string, never the literal word "null"', async () => {
    apiFetch.mockResolvedValue(
      ok({
        products: {
          p1: {
            lines: [
              {
                po_number: 'PO-100', supplier_name: null, qty: 5, unit_cost: null,
                currency: null, order_date: null, expected_date: null, status: null,
              },
            ],
          },
        },
      }),
    );
    const result = await getPoHistoryToPool('run-1', 'p1', 'BRW');
    expect(result.history[0].status).toBe('');
  });

  it('a non-ok response is surfaced through extractApiError', async () => {
    apiFetch.mockResolvedValue(fail('Server error.', 500));
    await expect(getPoHistoryToPool('run-1', 'p1', 'BRW')).rejects.toThrow('Server error.');
  });
});
