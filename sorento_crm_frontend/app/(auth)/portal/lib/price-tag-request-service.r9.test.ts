/**
 * The portal half of r9: Send, the comment list, the print choice and Collect
 * (AC-S2-3, AC-S3-1, AC-S3-6).
 *
 * Phase 1 answered four of these from in-memory stores so the whole journey
 * could be walked before a table, a column or two statuses existed. Phase 2
 * swaps each body for the real call and no caller changes, so what is asserted
 * here is the wire.
 *
 * The one that must not drift is Send: it is ONE call for the whole round. The
 * pins are placed locally and nothing reaches the server until the salesperson
 * presses the button, which is why they can put five pins down, delete two, and
 * the request changes state exactly once.
 *
 * RED before the coder starts: `requestChanges`, `listReviewComments` and
 * `collectRequest` never call the network, and `updateRequest` drops
 * `print_by` into a local override.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('./portal-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./portal-client')>();
  return { ...actual, portalFetch: vi.fn() };
});

import { portalFetch } from './portal-client';
import {
  collectRequest,
  listReviewComments,
  requestChanges,
  updateRequest,
} from './price-tag-request-service';

const mockFetch = vi.mocked(portalFetch);

const BASE = '/api/v1/public/portal/submissions/price_tag_request';

function ok(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as never;
}

function fail(status: number, message: string) {
  return { ok: false, status, json: async () => ({ message }) } as never;
}

const PIN = {
  line_id: 'line-1',
  x: 0.25,
  y: 0.5,
  w: 0,
  h: 0,
  body: 'Make the price bigger',
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe('requestChanges (AC-S2-3)', () => {
  it('sends the whole round in ONE call', async () => {
    mockFetch.mockResolvedValue(
      ok({ status: 'changes_requested', round: 1, comments: [] }),
    );

    await requestChanges('req-1', {
      comments: [PIN, { ...PIN, body: 'Move the logo', w: 0.2, h: 0.1 }],
      note: 'Overall it is too busy',
    });

    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(mockFetch.mock.calls[0][0]).toBe(`${BASE}/req-1/request-changes`);
    const init = mockFetch.mock.calls[0][1] as RequestInit;
    expect(init.method).toBe('POST');
    const body = JSON.parse(init.body as string);
    expect(body.comments).toHaveLength(2);
    expect(body.comments[0]).toMatchObject({ line_id: 'line-1', x: 0.25, y: 0.5 });
    expect(body.note).toBe('Overall it is too busy');
  });

  it('answers with the status and the rows the server created', async () => {
    mockFetch.mockResolvedValue(
      ok({
        status: 'changes_requested',
        round: 2,
        comments: [{ id: 'c1', body: 'Make the price bigger', round: 2 }],
      }),
    );

    const result = await requestChanges('req-1', { comments: [PIN] });

    expect(result.status).toBe('changes_requested');
    expect(result.comments).toHaveLength(1);
    expect(result.comments[0].id).toBe('c1');
  });

  it('raises the server refusal rather than reporting a Send that did not happen', async () => {
    mockFetch.mockResolvedValue(fail(409, 'This design is not waiting on you'));

    await expect(requestChanges('req-1', { comments: [PIN] })).rejects.toThrow(
      'This design is not waiting on you',
    );
  });
});

describe('listReviewComments (AC-S2-3)', () => {
  it('reads the portal review-comments route', async () => {
    mockFetch.mockResolvedValue(ok([{ id: 'c1', round: 1 }]));

    const rows = await listReviewComments('req-1');

    expect(mockFetch.mock.calls[0][0]).toBe(`${BASE}/req-1/review-comments`);
    expect(rows).toHaveLength(1);
  });
});

describe('collectRequest (AC-S3-6)', () => {
  it('posts the hand-over confirmation', async () => {
    mockFetch.mockResolvedValue(ok({ status: 'collected' }));

    const result = await collectRequest('req-1');

    expect(mockFetch.mock.calls[0][0]).toBe(`${BASE}/req-1/collect`);
    expect((mockFetch.mock.calls[0][1] as RequestInit).method).toBe('POST');
    expect(result.status).toBe('collected');
  });

  it('raises when the request is not waiting to be collected', async () => {
    mockFetch.mockResolvedValue(fail(409, 'These tags are not ready yet'));

    await expect(collectRequest('req-1')).rejects.toThrow(
      'These tags are not ready yet',
    );
  });
});

describe('print_by on the wire (AC-S3-1)', () => {
  it('travels in the PUT body and comes back on the response', async () => {
    mockFetch.mockResolvedValue(
      ok({ id: 'req-1', print_by: 'office', debtor_name: 'ZZT Dealer' }),
    );

    const updated = await updateRequest('req-1', {
      debtor_name: 'ZZT Dealer',
      print_by: 'office',
    } as never);

    const init = mockFetch.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(init.body as string).print_by).toBe('office');
    expect((updated as { print_by?: string }).print_by).toBe('office');
  });
});
