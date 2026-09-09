/**
 * S2 (AC-B7) - the dismiss/undo call shape: the same path, POSTed to dismiss and DELETEd to
 * undo. The mock store behind this service is gone; both functions reach `apiFetch`.
 *
 * The row's own Dismiss button no longer calls the POST directly - it parks
 * `proforma_invoice_packing_line.dismiss` as a pending action and the server applies it
 * when the window lapses (ruling 5). This is the route behind that action, and the one an
 * "Undo dismiss" on an already-dismissed row calls.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

import {
  dismissPackingLine,
  undoDismissPackingLine,
} from './proformaInvoicePackingService';

function jsonResponse(body: unknown, status = 200) {
  const headers = new Headers({ 'content-type': 'application/json' });
  return {
    ok: status < 400,
    status,
    headers,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response;
}

beforeEach(() => {
  apiFetch.mockReset();
  apiFetch.mockResolvedValue(jsonResponse({}));
});

describe('dismissPackingLine - real backend contract', () => {
  it('POSTs .../packing-lines/{row_id}/dismiss', async () => {
    await dismissPackingLine('inv-1', 'row-1');

    expect(apiFetch).toHaveBeenCalledWith(
      '/api/v1/scm/proforma-invoices/inv-1/packing-lines/row-1/dismiss',
      expect.objectContaining({ method: 'POST' }),
    );
  });
});

describe('undoDismissPackingLine - real backend contract', () => {
  it('DELETEs .../packing-lines/{row_id}/dismiss to undo, within the pending window', async () => {
    await undoDismissPackingLine('inv-1', 'row-1');

    expect(apiFetch).toHaveBeenCalledWith(
      '/api/v1/scm/proforma-invoices/inv-1/packing-lines/row-1/dismiss',
      expect.objectContaining({ method: 'DELETE' }),
    );
  });
});
