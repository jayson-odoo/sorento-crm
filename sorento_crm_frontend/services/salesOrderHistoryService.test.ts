import { beforeEach, describe, expect, it, vi } from 'vitest';

/** STANDARD-HISTORY wave 2 (AC-SH-W2-1): the two reads call the contract's routes. */
const apiFetch = vi.hoisted(() => vi.fn());
vi.mock('@/lib/api', () => ({ apiFetch: (...args: unknown[]) => apiFetch(...args) }));

import { getProjectSalesOrderHistory, getScmSalesOrderHistory } from './salesOrderHistoryService';

describe('salesOrderHistoryService', () => {
  beforeEach(() => apiFetch.mockReset());

  it('getProjectSalesOrderHistory GETs the project sales order history', async () => {
    apiFetch.mockResolvedValue({ ok: true, json: async () => ({ events: [] }) });
    await expect(getProjectSalesOrderHistory('pso-1')).resolves.toEqual({ events: [] });
    expect(apiFetch.mock.calls[0][0]).toBe('/api/v1/project-sales/sales-orders/pso-1/history');
  });

  it('getScmSalesOrderHistory GETs the SCM sales order history', async () => {
    apiFetch.mockResolvedValue({ ok: true, json: async () => ({ events: [] }) });
    await expect(getScmSalesOrderHistory('so-1')).resolves.toEqual({ events: [] });
    expect(apiFetch.mock.calls[0][0]).toBe('/api/v1/scm/sales-orders/so-1/history');
  });

  it('throws the server message when the read fails', async () => {
    apiFetch.mockResolvedValue({ ok: false, status: 404, json: async () => ({ detail: 'Sales order not found' }) });
    await expect(getProjectSalesOrderHistory('x')).rejects.toThrow();
  });
});
