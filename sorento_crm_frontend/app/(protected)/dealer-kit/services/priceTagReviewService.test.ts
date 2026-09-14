/**
 * The CRM's door to the review comments (r9 S2/D6, AC-S2-5).
 *
 * Phase 1 answered both functions from the in-memory store in
 * `lib/dealer-kit/review-comments.ts`, which is what let the whole loop be
 * walked before the table existed. Phase 2's job is to swap each body for the
 * real call WITHOUT changing a single caller, so this file asserts the wire:
 * the exact path, the method, and the row coming straight back out.
 *
 * RED before the coder starts: neither function touches `apiFetch` today.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));

import { apiFetch } from '@/lib/api';
import {
  listReviewComments,
  setReviewCommentResolved,
} from './priceTagReviewService';
import type { ReviewComment } from '@/lib/dealer-kit/review-comments';

const mockFetch = vi.mocked(apiFetch);

const ROW: ReviewComment = {
  id: 'comment-1',
  request_id: 'req-1',
  line_id: 'line-1',
  round: 1,
  x: 0.25,
  y: 0.5,
  w: 0,
  h: 0,
  body: 'Make the price bigger',
  author_name: 'ZZT Sales Sam',
  created_at: '2026-09-14T00:00:00Z',
  resolved_at: null,
  resolved_by_name: null,
};

function ok(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as never;
}

function fail(status: number, message: string) {
  // `extractApiError` reads `content-type` FIRST and only parses JSON when it
  // says so; a stub without headers falls into the text branch and answers the
  // fallback instead of the server's message (repo convention, see
  // app/(protected)/sla-management/message-snippets/services/messageSnippetService.test.ts).
  return {
    ok: false,
    status,
    headers: new Headers({ 'content-type': 'application/json' }),
    json: async () => ({ message }),
    text: async () => JSON.stringify({ message }),
  } as never;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('listReviewComments', () => {
  it('reads the request own review-comments route', async () => {
    mockFetch.mockResolvedValue(ok([ROW]));

    const rows = await listReviewComments('req-1');

    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(mockFetch.mock.calls[0][0]).toBe(
      '/api/v1/dealer-kit/price-tag-requests/req-1/review-comments',
    );
    expect(rows).toEqual([ROW]);
  });

  it('escapes the id rather than pasting it into the path raw', async () => {
    mockFetch.mockResolvedValue(ok([]));

    await listReviewComments('req 1/../secrets');

    expect(mockFetch.mock.calls[0][0]).toBe(
      '/api/v1/dealer-kit/price-tag-requests/req%201%2F..%2Fsecrets/review-comments',
    );
  });

  it('reports the server message rather than a blank list on failure', async () => {
    mockFetch.mockResolvedValue(fail(403, 'You cannot see this request'));

    await expect(listReviewComments('req-1')).rejects.toThrow(
      'You cannot see this request',
    );
  });
});

describe('setReviewCommentResolved', () => {
  it('PATCHes the comment with the new resolved state', async () => {
    mockFetch.mockResolvedValue(
      ok({ ...ROW, resolved_at: '2026-09-14T02:00:00Z', resolved_by_name: 'Mei' }),
    );

    const updated = await setReviewCommentResolved('req-1', 'comment-1', true);

    expect(mockFetch.mock.calls[0][0]).toBe(
      '/api/v1/dealer-kit/price-tag-requests/req-1/review-comments/comment-1',
    );
    const init = mockFetch.mock.calls[0][1] as RequestInit;
    expect(init.method).toBe('PATCH');
    expect(JSON.parse(init.body as string)).toEqual({ resolved: true });
    expect(updated?.resolved_by_name).toBe('Mei');
  });

  it('un-ticking sends resolved false', async () => {
    mockFetch.mockResolvedValue(ok(ROW));

    await setReviewCommentResolved('req-1', 'comment-1', false);

    const init = mockFetch.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(init.body as string)).toEqual({ resolved: false });
  });

  it('surfaces the 403 a portal contact gets rather than pretending it worked', async () => {
    mockFetch.mockResolvedValue(
      fail(403, 'Only the office can close a change request'),
    );

    await expect(
      setReviewCommentResolved('req-1', 'comment-1', true),
    ).rejects.toThrow('Only the office can close a change request');
  });
});
