import { beforeEach, describe, expect, it, vi } from 'vitest';

// SALES-INSIGHTS-P2 contract: the leaderboard query string carries basis, by, channel, and the drill
// filters (person / customer / product, each repeated), and sends no date param for Undelivered "All open".

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

import { getLeaderboard } from './salesLeaderboardService';

const ok = () => new Response(JSON.stringify({ rows: [] }));
const urlOfCall = () => new URL(String(apiFetch.mock.calls[0][0]), 'http://x');

beforeEach(() => {
  apiFetch.mockReset();
  apiFetch.mockResolvedValue(ok());
});

describe('getLeaderboard insights params', () => {
  it('P1-1 / P10-1 sends basis and by', async () => {
    await getLeaderboard({
      basis: 'delivered',
      by: 'customer',
      date_from: '2026-10-01',
      date_to: '2026-10-31',
    } as never);
    const url = urlOfCall();
    expect(url.pathname).toBe('/api/v1/sales/leaderboard');
    expect(url.searchParams.get('basis')).toBe('delivered');
    expect(url.searchParams.get('by')).toBe('customer');
    expect(url.searchParams.get('date_from')).toBe('2026-10-01');
    expect(url.searchParams.get('date_to')).toBe('2026-10-31');
  });

  it('P9-1 repeats channel per value', async () => {
    await getLeaderboard({
      basis: 'invoiced',
      by: 'channel',
      date_from: '2026-10-01',
      date_to: '2026-10-31',
      channel: ['dealer', 'no_sales_order'],
    } as never);
    expect(urlOfCall().searchParams.getAll('channel')).toEqual(['dealer', 'no_sales_order']);
  });

  it('P2-1 repeats the person, customer and product drill filters', async () => {
    await getLeaderboard({
      basis: 'invoiced',
      by: 'product',
      date_from: '2026-10-01',
      date_to: '2026-10-31',
      person: ['SEAN I', 'LCL'],
      customer: ['c-1', 'c-2'],
      product: ['p-1'],
    } as never);
    const sp = urlOfCall().searchParams;
    expect(sp.getAll('person')).toEqual(['SEAN I', 'LCL']);
    expect(sp.getAll('customer')).toEqual(['c-1', 'c-2']);
    expect(sp.getAll('product')).toEqual(['p-1']);
  });

  it('P10-2 omits every date param for Undelivered all open', async () => {
    await getLeaderboard({ basis: 'outstanding', by: 'person' } as never);
    const sp = urlOfCall().searchParams;
    expect(sp.get('basis')).toBe('outstanding');
    expect(sp.has('date_from')).toBe(false);
    expect(sp.has('date_to')).toBe(false);
    expect(sp.has('previous_from')).toBe(false);
    expect(sp.has('previous_to')).toBe(false);
  });

  it('omits empty drill and channel arrays', async () => {
    await getLeaderboard({
      basis: 'invoiced',
      by: 'person',
      date_from: '2026-10-01',
      date_to: '2026-10-31',
      channel: [],
      person: [],
      customer: [],
      product: [],
    } as never);
    const sp = urlOfCall().searchParams;
    for (const key of ['channel', 'person', 'customer', 'product']) expect(sp.has(key)).toBe(false);
  });
});

describe('getLeaderboard fix round 2 params', () => {
  it('7a / 7b repeats company and sends sort and dir', async () => {
    await getLeaderboard({
      basis: 'invoiced',
      by: 'customer',
      date_from: '2026-10-01',
      date_to: '2026-10-31',
      company: ['SOR', 'MCH'],
      sort: 'name',
      dir: 'desc',
    } as never);
    const sp = urlOfCall().searchParams;
    expect(sp.getAll('company')).toEqual(['SOR', 'MCH']);
    expect([sp.get('sort'), sp.get('dir')]).toEqual(['name', 'desc']);
  });

  it('omits sort and dir at the default', async () => {
    await getLeaderboard({ basis: 'invoiced', by: 'person', date_from: '2026-10-01', date_to: '2026-10-31', sort: 'rank', dir: 'asc' } as never);
    const sp = urlOfCall().searchParams;
    expect(sp.has('sort')).toBe(false);
    expect(sp.has('dir')).toBe(false);
  });
});
