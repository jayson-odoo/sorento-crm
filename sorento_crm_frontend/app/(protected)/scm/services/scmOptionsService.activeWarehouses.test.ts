import { beforeEach, describe, expect, it, vi } from 'vitest';

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }));
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetchMock(...a) }));

import { getActiveWarehouseOptions, getWarehouseOptions } from './scmOptionsService';

function ok(data: unknown) {
  return { ok: true, json: async () => ({ data }) };
}

beforeEach(() => {
  apiFetchMock.mockReset();
  apiFetchMock.mockResolvedValue(ok([{ warehouse_code: 'BRW', warehouse_name: 'Butterworth' }]));
});

describe('SCM-INACTIVE-LOCATIONS: scope pickers ask for active locations only', () => {
  it('getActiveWarehouseOptions passes active_only=true', async () => {
    const opts = await getActiveWarehouseOptions();
    const url = new URL(String(apiFetchMock.mock.calls[0][0]), 'http://x');
    expect(url.pathname).toBe('/api/v1/scm/dashboard/warehouses');
    expect(url.searchParams.get('active_only')).toBe('true');
    expect(opts).toEqual([{ value: 'BRW', label: 'Butterworth' }]);
  });

  it('getWarehouseOptions (code-to-name lookups) stays unfiltered', async () => {
    await getWarehouseOptions();
    const url = new URL(String(apiFetchMock.mock.calls[0][0]), 'http://x');
    expect(url.searchParams.get('active_only')).toBeNull();
  });
});
