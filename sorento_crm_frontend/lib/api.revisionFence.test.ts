/**
 * `apiFetch` is the seam the revision fence is wired into (UAC C-bis).
 *
 * These assert the wire, not the helpers: reading a stock inquiry has to make
 * the very next write carry `X-Revision-No`, and a 409 against a superseded
 * version has to reach the caller as the server's own sentence AND refresh the
 * record. If either half regresses the fence is inert again, which is exactly
 * the state this work found it in.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

import { apiFetch } from './api';
import {
  clearRememberedRevisions,
  registerRevisionStaleHandler,
} from './revision-fence';

const SI = '11111111-2222-3333-4444-555555555555';
const SENTENCE =
  'This stock inquiry was revised while you were working on it. Reload to see revision 2.';

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

/** Header value the last `fetch` call carried, whichever shape init used. */
function sentHeader(call: [RequestInfo, RequestInit | undefined], name: string): string | null {
  const headers = call[1]?.headers;
  if (!headers) return null;
  return new Headers(headers as HeadersInit).get(name);
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  clearRememberedRevisions();
  registerRevisionStaleHandler(null);
  fetchMock = vi.fn(async (input: RequestInfo) => {
    // The token mint every apiFetch does first; irrelevant to the fence.
    if (String(input).includes('/api/auth/token')) return json({ token: null });
    return json({});
  });
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  clearRememberedRevisions();
  registerRevisionStaleHandler(null);
});

/** Every `fetch` the fenced calls made, token mints filtered out. */
function apiCalls(): [RequestInfo, RequestInit | undefined][] {
  return fetchMock.mock.calls.filter(
    (c) => !String(c[0]).includes('/api/auth/token'),
  ) as [RequestInfo, RequestInit | undefined][];
}

describe('apiFetch + revision fence: sending the header', () => {
  it('sends the revision the detail page was showing on the next write', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo) => {
      if (String(input).includes('/api/auth/token')) return json({ token: null });
      if (String(input).endsWith(`/stock-inquiries/${SI}`)) {
        return json({ id: SI, inquiry_number: 'SI-26-0184', revision_no: 2 });
      }
      return json({ id: SI });
    });

    await apiFetch(`/api/v1/procurement/stock-inquiries/${SI}`);
    await apiFetch(`/api/v1/procurement/stock-inquiries/${SI}`, {
      method: 'PUT',
      body: JSON.stringify({ purchasing_response: 'In stock' }),
    });

    const write = apiCalls().at(-1)!;
    expect(sentHeader(write, 'X-Revision-No')).toBe('2');
  });

  it('sends it on the action sub-paths too, not just the PUT', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo) => {
      if (String(input).includes('/api/auth/token')) return json({ token: null });
      if (String(input).endsWith(`/stock-inquiries/${SI}`)) {
        return json({ id: SI, revision_no: 5 });
      }
      return json({});
    });

    await apiFetch(`/api/v1/procurement/stock-inquiries/${SI}`);
    await apiFetch(`/api/v1/procurement/stock-inquiries/${SI}/update-and-reply`, {
      method: 'POST',
      body: '{}',
    });

    expect(sentHeader(apiCalls().at(-1)!, 'X-Revision-No')).toBe('5');
  });

  it('sends it on a FormData upload, whose init builds a Headers instance', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo) => {
      if (String(input).includes('/api/auth/token')) return json({ token: 'jwt.jwt.jwt' });
      if (String(input).endsWith(`/stock-inquiries/${SI}`)) {
        return json({ id: SI, revision_no: 1 });
      }
      return json({});
    });

    await apiFetch(`/api/v1/procurement/stock-inquiries/${SI}`);
    await apiFetch(`/api/v1/procurement/stock-inquiries/${SI}/response-attachments`, {
      method: 'POST',
      body: new FormData(),
    });

    expect(sentHeader(apiCalls().at(-1)!, 'X-Revision-No')).toBe('1');
  });

  it('picks the revision up off the LIST, so a row action is fenced as well', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo) => {
      if (String(input).includes('/api/auth/token')) return json({ token: null });
      if (String(input).includes('/stock-inquiries?')) {
        return json({ items: [{ id: SI, revision_no: 3 }] });
      }
      return json({});
    });

    await apiFetch('/api/v1/procurement/stock-inquiries?page=1&limit=25');
    await apiFetch(`/api/v1/procurement/stock-inquiries/${SI}`, { method: 'DELETE' });

    expect(sentHeader(apiCalls().at(-1)!, 'X-Revision-No')).toBe('3');
  });

  it('sends no header for a record never read - absent means unfenced, on purpose', async () => {
    await apiFetch(`/api/v1/procurement/stock-inquiries/${SI}/void`, {
      method: 'POST',
      body: '{}',
    });
    expect(sentHeader(apiCalls().at(-1)!, 'X-Revision-No')).toBeNull();
  });

  it('leaves an unfenced resource alone', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo) => {
      if (String(input).includes('/api/auth/token')) return json({ token: null });
      return json({ id: SI, revision_no: 9 });
    });
    await apiFetch(`/api/v1/master-data/products/${SI}`);
    await apiFetch(`/api/v1/master-data/products/${SI}`, { method: 'PUT', body: '{}' });
    expect(sentHeader(apiCalls().at(-1)!, 'X-Revision-No')).toBeNull();
  });

  /**
   * The two halves asserted together, from ONE primed read, so the fix cannot
   * degrade into "unfence everything": the chat send the backend leaves open must
   * carry no header, and a real fenced action in the very same session must.
   */
  it('skips the open chat send but still stamps a fenced action in the same session', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo, init?: RequestInit) => {
      if (String(input).includes('/api/auth/token')) return json({ token: null });
      if ((init?.method ?? 'GET') === 'GET') return json({ id: SI, revision_no: 4 });
      return json({});
    });

    await apiFetch(`/api/v1/procurement/stock-inquiries/${SI}`);

    await apiFetch(`/api/v1/procurement/stock-inquiries/${SI}/conversation/send-message`, {
      method: 'POST',
      body: JSON.stringify({ text: 'Any update on this?' }),
    });
    expect(sentHeader(apiCalls().at(-1)!, 'X-Revision-No')).toBeNull();

    await apiFetch(`/api/v1/procurement/stock-inquiries/${SI}/void`, {
      method: 'POST',
      body: '{}',
    });
    expect(sentHeader(apiCalls().at(-1)!, 'X-Revision-No')).toBe('4');
  });
});

describe('apiFetch + revision fence: the refusal', () => {
  async function primeThenWrite() {
    fetchMock.mockImplementation(async (input: RequestInfo, init?: RequestInit) => {
      if (String(input).includes('/api/auth/token')) return json({ token: null });
      if ((init?.method ?? 'GET') === 'GET') return json({ id: SI, revision_no: 1 });
      return json({ detail: SENTENCE }, 409);
    });
    await apiFetch(`/api/v1/procurement/stock-inquiries/${SI}`);
    return apiFetch(`/api/v1/procurement/stock-inquiries/${SI}`, {
      method: 'PUT',
      body: '{}',
    });
  }

  it("surfaces the server's sentence to every way a service reads the body", async () => {
    const response = await primeThenWrite();
    expect(response.status).toBe(409);
    const body = await response.json();
    expect(body.detail).toBe(SENTENCE);
    // The hand-rolled readers in the feature services fall back to `message`;
    // without this they would throw `Error(undefined)` and toast nothing.
    expect(body.message).toBe(SENTENCE);
  });

  it('refreshes the record so the user lands on the new revision', async () => {
    const onStale = vi.fn();
    registerRevisionStaleHandler(onStale);
    await primeThenWrite();
    expect(onStale).toHaveBeenCalledWith(SI);
  });

  it('does not touch a 409 on a request we never fenced', async () => {
    const onStale = vi.fn();
    registerRevisionStaleHandler(onStale);
    fetchMock.mockImplementation(async (input: RequestInfo) => {
      if (String(input).includes('/api/auth/token')) return json({ token: null });
      return json({ detail: 'Duplicate' }, 409);
    });
    // Never read, so no header went out; this 409 belongs to something else.
    const response = await apiFetch(`/api/v1/procurement/stock-inquiries/${SI}`, {
      method: 'PUT',
      body: '{}',
    });
    expect(onStale).not.toHaveBeenCalled();
    expect(await response.json()).toEqual({ detail: 'Duplicate' });
  });

  /**
   * A 409 from an UNFENCED sub-route of a record we HAVE read.
   *
   * This is the case the blanket write matcher got wrong: the record was read, so a
   * revision was remembered, so any 409 from anything under it - a duplicate chat
   * send, an idempotency clash - was rewritten as "this record was revised" and
   * invalidated the whole query cache. The record being known is not licence to
   * claim every conflict under it.
   */
  it('passes a 409 from an open sub-route straight through', async () => {
    const onStale = vi.fn();
    registerRevisionStaleHandler(onStale);
    fetchMock.mockImplementation(async (input: RequestInfo, init?: RequestInit) => {
      if (String(input).includes('/api/auth/token')) return json({ token: null });
      if ((init?.method ?? 'GET') === 'GET') return json({ id: SI, revision_no: 2 });
      return json({ detail: 'A message is already being sent for this contact.' }, 409);
    });

    await apiFetch(`/api/v1/procurement/stock-inquiries/${SI}`);
    const response = await apiFetch(
      `/api/v1/procurement/stock-inquiries/${SI}/conversation/send-message`,
      { method: 'POST', body: JSON.stringify({ text: 'hello' }) },
    );

    expect(response.status).toBe(409);
    expect(await response.json()).toEqual({
      detail: 'A message is already being sent for this contact.',
    });
    expect(onStale).not.toHaveBeenCalled();
  });
});
