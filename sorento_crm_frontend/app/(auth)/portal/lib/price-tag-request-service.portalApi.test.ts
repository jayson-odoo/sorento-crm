/**
 * PORTAL-P4-REQUESTS S7b guard (stays green): while the CRM reuses the portal's price tag components, the
 * portal's own service must keep calling the PORTAL API with the portal token, never my-requests. Whoever makes
 * the base path injectable for the CRM must leave these defaults alone.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const portalFetch = vi.hoisted(() => vi.fn());
vi.mock('./portal-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./portal-client')>();
  return { ...actual, portalFetch };
});

import {
  approveRequest,
  listReviewComments,
  lookupLinePricing,
  lookupProductCombos,
  lookupTagItems,
  requestChanges,
} from './price-tag-request-service';

const ok = (b: unknown) => new Response(JSON.stringify(b), { status: 200, headers: { 'content-type': 'application/json' } });
const PORTAL = '/api/v1/public/portal';

beforeEach(() => {
  portalFetch.mockReset();
  portalFetch.mockImplementation(async () => ok([]));
});

describe('portal price tag service keeps the portal base', () => {
  it('request-changes posts the pinned body to the portal route', async () => {
    portalFetch.mockImplementation(async () => ok({ status: 'changes_requested', round: 1, comments: [] }));
    const payload = { comments: [{ tag_id: 't1', x: 0.25, y: 0.5, w: 0, h: 0, body: 'Bigger' }], note: 'n' };
    await requestChanges('req-1', payload);
    const [url, init] = portalFetch.mock.calls[0];
    expect(url).toBe(`${PORTAL}/submissions/price_tag_request/req-1/request-changes`);
    expect(JSON.parse(init.body)).toEqual(payload);
  });

  it('review-comments, approve, lookups and line-pricing all stay under /public/portal', async () => {
    portalFetch.mockImplementation(async () => ok({ status: 'approved', host_guarded: false, combos: [] }));
    await listReviewComments('req-1');
    await approveRequest('req-1');
    await lookupTagItems('sink');
    await lookupProductCombos('p-1');
    portalFetch.mockImplementation(async () => ok([]));
    await lookupLinePricing('list', []);
    const urls = portalFetch.mock.calls.map((c) => c[0] as string);
    expect(urls).toEqual([
      `${PORTAL}/submissions/price_tag_request/req-1/review-comments`,
      `${PORTAL}/submissions/price_tag_request/req-1/approve`,
      `${PORTAL}/lookups/price-tag-items?q=sink`,
      `${PORTAL}/lookups/product-combos/p-1`,
      `${PORTAL}/lookups/line-pricing`,
    ]);
    expect(urls.some((u) => u.includes('my-requests'))).toBe(false);
  });
});
