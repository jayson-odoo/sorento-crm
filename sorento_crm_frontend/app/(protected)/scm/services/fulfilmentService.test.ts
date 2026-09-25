import { describe, it, expect, vi, beforeEach } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

import { deleteSpo, getSupplierNotices, sendContainerRequest } from './fulfilmentService';

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
});

describe('deleteSpo', () => {
  it('DELETEs the shipment SPO route and returns what was deleted', async () => {
    apiFetch.mockResolvedValue(
      jsonResponse({
        shipment_id: 'ship-1',
        shipment_number: 'SH-1',
        deleted_po_numbers: ['CRM-SPO-0001'],
        deleted_spo_count: 1,
        deleted_allocation_count: 2,
      }),
    );

    const out = await deleteSpo('ship-1');

    expect(apiFetch).toHaveBeenCalledWith(
      '/api/v1/scm/inbound-shipments/ship-1/spo',
      expect.objectContaining({ method: 'DELETE' }),
    );
    expect(out.deleted_spo_count).toBe(1);
    expect(out.deleted_allocation_count).toBe(2);
  });

  it('throws the extracted API error on a refused (409) delete', async () => {
    apiFetch.mockResolvedValue(
      jsonResponse(
        { message: 'CRM-SPO-9999 was not created by Create SPO and cannot be deleted from this screen.' },
        409,
      ),
    );

    await expect(deleteSpo('ship-1')).rejects.toThrow(
      'CRM-SPO-9999 was not created by Create SPO and cannot be deleted from this screen.',
    );
  });
});

describe('getSupplierNotices', () => {
  it('asks for one plan\'s notices when the record page names its plan (R3/R11)', async () => {
    apiFetch.mockResolvedValue(jsonResponse({ data: [] }));

    await getSupplierNotices('sup-1', 'plan-1');

    expect(String(apiFetch.mock.calls[0][0])).toBe(
      '/api/v1/scm/supplier-notices?supplier_id=sup-1&loading_plan_id=plan-1',
    );
  });

  it('asks for the supplier\'s whole history when no plan is named', async () => {
    apiFetch.mockResolvedValue(jsonResponse({ data: [] }));

    await getSupplierNotices('sup-1');

    expect(String(apiFetch.mock.calls[0][0])).toBe(
      '/api/v1/scm/supplier-notices?supplier_id=sup-1',
    );
  });
});

describe('sendContainerRequest', () => {
  const notice = (over: Record<string, unknown>) => ({
    id: 'n-1',
    status: 'sent',
    status_reason: null,
    last_error: null,
    ...over,
  });

  it('raises the reason when the 201 carries a notice that never went out', async () => {
    apiFetch.mockResolvedValue(
      jsonResponse({
        notices: [notice({ status: 'failed', last_error: 'the outbox is not accepting mail' })],
        document_filename: 'container-request.pdf',
      }),
    );

    await expect(sendContainerRequest('plan-1', [])).rejects.toThrow(
      'the outbox is not accepting mail',
    );
  });

  it('returns the body when the notice went out', async () => {
    apiFetch.mockResolvedValue(
      jsonResponse({ notices: [notice({})], document_filename: 'container-request.pdf' }),
    );

    const out = await sendContainerRequest('plan-1', []);

    expect(out.notices[0].status).toBe('sent');
  });
});
