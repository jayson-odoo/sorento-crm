/**
 * CRM-side price tag review comments (r9 S2/D6).
 *
 * ## API contract
 *
 * ```
 * GET /api/v1/dealer-kit/price-tag-requests/{id}/review-comments
 *   200 ReviewComment[]        every round, oldest first
 *
 * PATCH /api/v1/dealer-kit/price-tag-requests/{id}/review-comments/{commentId}
 *   { resolved: boolean }
 *   200 ReviewComment          403 for anyone but a processor
 * ```
 *
 * The row shape and the portal half of the loop live in
 * `lib/dealer-kit/review-comments.ts`.
 */

import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type { ReviewComment } from '@/lib/dealer-kit/review-comments';

export type { ReviewComment };

const BASE = '/api/v1/dealer-kit/price-tag-requests';

export async function listReviewComments(
  requestId: string,
): Promise<ReviewComment[]> {
  const response = await apiFetch(
    `${BASE}/${encodeURIComponent(requestId)}/review-comments`,
  );
  if (!response.ok) {
    throw new Error(
      await extractApiError(response, 'Failed to load the change requests'),
    );
  }
  return response.json();
}

/** Tick a change request Done, or put it back. */
export async function setReviewCommentResolved(
  requestId: string,
  commentId: string,
  resolved: boolean,
): Promise<ReviewComment | null> {
  const response = await apiFetch(
    `${BASE}/${encodeURIComponent(requestId)}/review-comments/${encodeURIComponent(commentId)}`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ resolved }),
    },
  );
  if (!response.ok) {
    throw new Error(
      await extractApiError(response, 'Failed to update the change request'),
    );
  }
  return response.json();
}
