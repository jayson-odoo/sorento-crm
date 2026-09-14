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
 *   200 ReviewComment          403 for anyone but the assignee or a processor
 * ```
 *
 * The row shape and the portal half of the loop live in
 * `lib/dealer-kit/review-comments.ts`.
 *
 * PHASE 1: both functions answer from the in-memory store there, so the whole
 * review loop can be walked before the table exists. Each body becomes an
 * `apiFetch` in Phase 2 and no caller changes.
 */

import {
  mockListReviewComments,
  mockSetResolved,
  type ReviewComment,
} from '@/lib/dealer-kit/review-comments';

export type { ReviewComment };

export async function listReviewComments(
  requestId: string,
): Promise<ReviewComment[]> {
  return mockListReviewComments(requestId);
}

/** Tick a change request Done, or put it back. */
export async function setReviewCommentResolved(
  requestId: string,
  commentId: string,
  resolved: boolean,
): Promise<ReviewComment | null> {
  return mockSetResolved(requestId, commentId, resolved, 'You');
}
