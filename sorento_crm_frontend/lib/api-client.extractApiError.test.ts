/**
 * AFTER-SALES-P2 review round (item 6): `extractApiError` keeps its behaviour on main for a response that carries no
 * content-type. A missing header means "not JSON" (the proxy's and a bare 401's answer), never "assume JSON".
 */
import { describe, it, expect } from 'vitest';
import { extractApiError } from './api-client';

const NOT_SIGNED_IN = 'Not signed in or session expired. Please sign in again.';

describe('extractApiError without a JSON content-type', () => {
  it('an empty 401 with no content-type reads "Not signed in"', async () => {
    expect(await extractApiError(new Response(null, { status: 401 }), 'Failed')).toBe(NOT_SIGNED_IN);
  });

  it('an empty 401 with an empty body string reads "Not signed in"', async () => {
    expect(await extractApiError(new Response('', { status: 401, headers: { 'content-type': 'text/plain' } }), 'Failed')).toBe(NOT_SIGNED_IN);
  });

  it('a text/plain error body gives its text', async () => {
    const res = new Response('Upstream exploded', { status: 500, headers: { 'content-type': 'text/plain' } });
    expect(await extractApiError(res, 'Failed')).toBe('Upstream exploded');
  });

  it('a text body with NO content-type header still gives its text, not the fallback', async () => {
    const res = { ok: false, status: 500, headers: new Headers(), text: async () => 'Upstream exploded', json: async () => { throw new Error('not json'); } } as unknown as Response;
    expect(await extractApiError(res, 'Failed')).toBe('Upstream exploded');
  });

  it('an HTML 502 page with no content-type reads as a bad gateway', async () => {
    const res = { ok: false, status: 502, headers: new Headers(), text: async () => '<html><body>502</body></html>', json: async () => { throw new Error('x'); } } as unknown as Response;
    expect(await extractApiError(res, 'Failed')).toMatch(/Bad gateway \(502\)/);
  });

  it('a JSON body still gives its detail', async () => {
    const res = new Response(JSON.stringify({ detail: 'Nope' }), { status: 409, headers: { 'content-type': 'application/json' } });
    expect(await extractApiError(res, 'Failed')).toBe('Nope');
  });
});
