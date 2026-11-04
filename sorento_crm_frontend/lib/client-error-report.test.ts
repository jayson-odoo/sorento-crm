import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { buildClientErrorReport, reportClientError } from './client-error-report';

const fetchMock = vi.fn();

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
  window.history.replaceState(null, '', '/inventory/stock-inquiries?q=secret#frag');
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const posts = () => fetchMock.mock.calls.filter((c) => String(c[0]).includes('/client-errors'));

describe('reportClientError', () => {
  it('posts one report per error with a bearer token, path only', async () => {
    fetchMock.mockImplementation(async (url: string) =>
      url.includes('/api/auth/token') ? json({ token: 'tok' }) : new Response(null, { status: 204 }),
    );
    const err = new Error('boom');
    await reportClientError(err, 'global');
    await reportClientError(err, 'global');
    expect(posts()).toHaveLength(1);
    const [url, init] = posts()[0];
    expect(url).toBe('/api/v1/system/client-errors');
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer tok');
    const body = JSON.parse(init.body);
    expect(body.path).toBe('/inventory/stock-inquiries');
    expect(JSON.stringify(body)).not.toContain('secret');
    expect(body.message).toBe('boom');
    expect(body.boundary).toBe('global');
    expect(body.is_chunk_error).toBe(false);
    expect(init.keepalive).toBe(true);
  });

  it('signed out (no token): nothing is posted', async () => {
    fetchMock.mockResolvedValue(json({ error: 'No valid session' }, 401));
    await reportClientError(new Error('x'), 'protected');
    expect(posts()).toHaveLength(0);
  });

  it('retries without keepalive when the browser rejects it (older Safari)', async () => {
    let n = 0;
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url.includes('/api/auth/token')) return json({ token: 'tok' });
      n += 1;
      if (init?.keepalive) throw new TypeError('keepalive unsupported');
      return new Response(null, { status: 204 });
    });
    await reportClientError(new Error('y'), 'global');
    expect(n).toBe(2);
    expect(posts()[1][1].keepalive).toBeUndefined();
  });

  it('never throws when the network is down', async () => {
    fetchMock.mockRejectedValue(new TypeError('Load failed'));
    await expect(reportClientError(new Error('z'), 'global')).resolves.toBeUndefined();
  });
});

describe('buildClientErrorReport', () => {
  it('caps message and stack and flags chunk errors', () => {
    const e = new Error('Loading chunk 9 failed' + 'm'.repeat(5000));
    e.stack = 's'.repeat(20000);
    const r = buildClientErrorReport(e, 'global');
    expect(r.message.length).toBe(2000);
    expect(r.stack!.length).toBe(8000);
    expect(r.is_chunk_error).toBe(true);
  });
});
