/**
 * DEALER-PLANNING PR 2, R6: the list service sends the class filter on the wire.
 * Written test-first; `demand_class` is not a param of `listFulfilmentPlanning` yet.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

beforeEach(() => {
  vi.resetModules();
  vi.clearAllMocks();
});

describe('fulfilmentPlanningService demand_class', () => {
  const apiFetch = vi.fn();

  async function load() {
    vi.doMock('@/lib/api', () => ({ apiFetch: (...args: unknown[]) => apiFetch(...args) }));
    return import('./fulfilmentPlanningService');
  }

  const ok = { ok: true, json: async () => ({ data: [], pagination: { total: 0, page: 1, limit: 25 } }) } as Response;

  it('sends every chosen class', async () => {
    apiFetch.mockResolvedValue(ok);
    const { listFulfilmentPlanning } = await load();

    await listFulfilmentPlanning({ demand_class: ['project', 'retail'] } as never);

    const url = new URL(String(apiFetch.mock.calls[0][0]), 'http://x');
    const sent = url.searchParams.getAll('demand_class').flatMap((v) => v.split(','));
    expect(sent.sort()).toEqual(['project', 'retail']);
  });

  it('sends nothing when no class is chosen', async () => {
    apiFetch.mockResolvedValue(ok);
    const { listFulfilmentPlanning } = await load();

    await listFulfilmentPlanning({});

    expect(String(apiFetch.mock.calls[0][0])).not.toContain('demand_class');
  });
});
