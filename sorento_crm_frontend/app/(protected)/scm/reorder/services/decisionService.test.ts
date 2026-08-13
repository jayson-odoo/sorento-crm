/**
 * SCM M4 Slice B - decisionService (Accept / Adjust / Reject / bulk + list).
 * Pins the FE→BE contract documented at the top of `decisionService.ts`:
 * every call hits the right method + path + body, and a non-ok response is
 * surfaced via `extractApiError`.
 *   AC-M4.5 (accept → draft PO)  · AC-M4.7 (adjust: qty + supplier + reason)
 *   AC-M4.8 (reject: required reason) · AC-M4.9 (bulk accept / bulk reject)
 *   AC-M4.14 (decisions drive the per-row badge)
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

import {
  acceptRecommendation,
  adjustRecommendation,
  bulkAcceptFunded,
  bulkRejectRecommendations,
  getRecommendationDecisions,
  rejectRecommendation,
} from './decisionService';
import type { ReorderRecommendation } from '../types/reorder.types';

function ok(body: unknown) {
  return {
    ok: true,
    status: 200,
    headers: { get: () => 'application/json' },
    json: async () => body,
  } as unknown as Response;
}

/** A non-ok JSON response whose `detail` extractApiError should surface. */
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

const rec = (over: Partial<ReorderRecommendation> = {}) =>
  ({ id: 'rec-1', sku: 'CW-BASIN-450', ...over }) as ReorderRecommendation;

beforeEach(() => apiFetch.mockReset());

describe('decisionService - accept (AC-M4.5)', () => {
  it('POSTs to /recommendations/{id}/accept and returns the draft PO ref', async () => {
    apiFetch.mockResolvedValue(
      ok({ draft_po_number: 'PO-DRAFT-0007', draft_po_id: 'po-7', supplier_name: 'Acme' }),
    );
    const res = await acceptRecommendation(rec({ id: 'rec-9' }));
    expect(calledUrl().pathname).toBe('/api/v1/scm/recommendations/rec-9/accept');
    expect(lastInit().method).toBe('POST');
    expect(res).toMatchObject({ draft_po_number: 'PO-DRAFT-0007', supplier_name: 'Acme' });
  });

  it('surfaces the backend error message on a non-ok response', async () => {
    apiFetch.mockResolvedValue(fail('Recommendation already decided', 409));
    await expect(acceptRecommendation(rec())).rejects.toThrow('Recommendation already decided');
  });
});

describe('decisionService - adjust (AC-M4.7)', () => {
  it('POSTs qty + supplier switch + reason, mapping supplier_code → override_supplier_id', async () => {
    apiFetch.mockResolvedValue(
      ok({ draft_po_number: 'PO-DRAFT-0008', draft_po_id: 'po-8', supplier_name: 'Beta' }),
    );
    await adjustRecommendation(rec({ id: 'rec-3' }), {
      override_qty: 500,
      override_supplier_code: 'SUP-BETA',
      reason_text: 'cheaper alternative',
    });
    expect(calledUrl().pathname).toBe('/api/v1/scm/recommendations/rec-3/adjust');
    expect(lastInit().method).toBe('POST');
    expect(JSON.parse(String(lastInit().body))).toEqual({
      override_qty: 500,
      override_supplier_id: 'SUP-BETA',
      reason_text: 'cheaper alternative',
    });
  });

  it('sends a null supplier when the proposed supplier stands (qty-only adjust)', async () => {
    apiFetch.mockResolvedValue(
      ok({ draft_po_number: 'PO-DRAFT-0009', draft_po_id: 'po-9', supplier_name: 'Acme' }),
    );
    await adjustRecommendation(rec(), {
      override_qty: 120,
      override_supplier_code: null,
      reason_text: 'MOQ changed',
    });
    expect(JSON.parse(String(lastInit().body)).override_supplier_id).toBeNull();
  });

  it('surfaces the backend error on failure', async () => {
    apiFetch.mockResolvedValue(fail('Supplier has no cost'));
    await expect(
      adjustRecommendation(rec(), { override_qty: 1, override_supplier_code: null, reason_text: 'x' }),
    ).rejects.toThrow('Supplier has no cost');
  });
});

describe('decisionService - reject (AC-M4.8)', () => {
  it('POSTs the required reason to /reject', async () => {
    apiFetch.mockResolvedValue(ok({}));
    await rejectRecommendation(rec({ id: 'rec-5' }), { reason_text: 'discontinued' });
    expect(calledUrl().pathname).toBe('/api/v1/scm/recommendations/rec-5/reject');
    expect(lastInit().method).toBe('POST');
    expect(JSON.parse(String(lastInit().body))).toEqual({ reason_text: 'discontinued' });
  });

  it('surfaces the backend error on failure', async () => {
    apiFetch.mockResolvedValue(fail('Not allowed'));
    await expect(rejectRecommendation(rec(), { reason_text: 'x' })).rejects.toThrow('Not allowed');
  });
});

describe('decisionService - bulk accept / reject (AC-M4.9)', () => {
  it('bulk-accept POSTs the run id + selected ids', async () => {
    apiFetch.mockResolvedValue(ok({ accepted_count: 3, po_count: 2 }));
    const res = await bulkAcceptFunded('run-1', [rec({ id: 'a' }), rec({ id: 'b' }), rec({ id: 'c' })]);
    expect(calledUrl().pathname).toBe('/api/v1/scm/recommendations/bulk-accept');
    expect(JSON.parse(String(lastInit().body))).toEqual({ run_id: 'run-1', ids: ['a', 'b', 'c'] });
    expect(res).toEqual({ accepted_count: 3, po_count: 2 });
  });

  it('bulk-reject POSTs the run id + ids + one shared reason', async () => {
    apiFetch.mockResolvedValue(ok({ rejected_count: 2 }));
    const res = await bulkRejectRecommendations('run-1', [rec({ id: 'a' }), rec({ id: 'b' })], 'overstocked');
    expect(calledUrl().pathname).toBe('/api/v1/scm/recommendations/bulk-reject');
    expect(JSON.parse(String(lastInit().body))).toEqual({
      run_id: 'run-1',
      ids: ['a', 'b'],
      reason_text: 'overstocked',
    });
    expect(res).toEqual({ rejected_count: 2 });
  });

  it('surfaces the backend error on a bulk failure', async () => {
    apiFetch.mockResolvedValue(fail('Budget exceeded'));
    await expect(bulkAcceptFunded('run-1', [rec()])).rejects.toThrow('Budget exceeded');
  });
});

describe('decisionService - list decisions (AC-M4.14)', () => {
  it('GETs /reorder-runs/{run_id}/decisions and unwraps the data envelope', async () => {
    apiFetch.mockResolvedValue(
      ok({
        data: [
          {
            recommendation_id: 'rec-1',
            status: 'accepted',
            override_qty: null,
            override_supplier_code: null,
            override_supplier_name: null,
            reason_text: null,
            draft_po_number: 'PO-DRAFT-0001',
            draft_po_id: 'po-1',
          },
        ],
      }),
    );
    const decisions = await getRecommendationDecisions('run-7');
    expect(calledUrl().pathname).toBe('/api/v1/scm/reorder-runs/run-7/decisions');
    expect(decisions).toHaveLength(1);
    expect(decisions[0]).toMatchObject({ recommendation_id: 'rec-1', status: 'accepted' });
  });

  it('surfaces the backend error on failure', async () => {
    apiFetch.mockResolvedValue(fail('Run not found', 404));
    await expect(getRecommendationDecisions('run-x')).rejects.toThrow('Run not found');
  });
});
