/** NON-CANCELLABLE-ITEMS: the bulk lines save resends with the override reason as a query param. */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiFetch = vi.hoisted(() => vi.fn());
vi.mock('@/lib/api', () => ({ apiFetch }));

import { replaceQuotationLines } from './projectService';

beforeEach(() => apiFetch.mockReset());

describe('replaceQuotationLines', () => {
  it('sends no query param without a reason and with one when given', async () => {
    apiFetch.mockImplementation(async () =>
      new Response(JSON.stringify({ data: [] }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    );
    await replaceQuotationLines('v1', []);
    expect(apiFetch.mock.calls[0][0]).toMatch(/\/quotation-versions\/v1\/lines$/);
    await replaceQuotationLines('v1', [], 'Customer agreed');
    expect(apiFetch.mock.calls[1][0]).toMatch(
      /\/lines\?non_cancellable_override_reason=Customer%20agreed$/,
    );
  });
});
