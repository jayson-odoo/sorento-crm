/**
 * Pinned change requests on a tag sheet design (r9 S2/D4-D6).
 *
 * A salesperson does not describe a change, they point at it: a click on the
 * tag drops a pin, a drag draws a box, and the comment hangs off that spot. The
 * anchor is stored as FRACTIONS of the tag's own box, not page millimetres, so
 * re-arranging the sheet, paging, or zooming leaves every pin exactly on the
 * part of the tag it was put on.
 *
 * ## Expected API contract (Phase 1: the store below stands in)
 *
 * ```
 * POST /api/v1/public/portal/submissions/price_tag_request/{id}/request-changes
 *   {
 *     comments: [{ line_id: string | null, x: number, y: number,
 *                  w: number, h: number, body: string }],   // fractions 0..1
 *     note?: string          // the general comment, optional
 *   }
 *   200 { status: "changes_requested", round: number, comments: ReviewComment[] }
 *   The legacy body `{ note }` alone stays accepted for one release and lands
 *   as one general comment (line_id null, no fractions).
 *
 * GET /api/v1/public/portal/submissions/price_tag_request/{id}/review-comments
 *   200 ReviewComment[]      // every round, oldest first; the salesperson's
 *                            // earlier rounds render grey (D6)
 *
 * GET /api/v1/dealer-kit/price-tag-requests/{id}/review-comments
 *   200 ReviewComment[]
 *
 * PATCH /api/v1/dealer-kit/price-tag-requests/{id}/review-comments/{commentId}
 *   { resolved: boolean }
 *   200 ReviewComment        // 403 for anyone but the assignee or a processor
 * ```
 *
 * `ReviewComment` is one `price_tag_review_comments` row: fractions null on a
 * general comment, `round` = the number of proof_ready snapshots when it was
 * sent, `resolved_at` set once marketing ticks it Done.
 */

import type { TagSheetDoc } from '@/lib/dealer-kit/tag-template-types';

export interface ReviewComment {
  id: string;
  request_id: string;
  /** Null for a general comment - it points at no tag. */
  line_id: string | null;
  round: number;
  /** Fractions of the tag box, 0..1. Null on a general comment. */
  x: number | null;
  y: number | null;
  /** 0 for a point pin, > 0 for a box. */
  w: number | null;
  h: number | null;
  body: string;
  author_name: string | null;
  created_at: string;
  resolved_at: string | null;
  resolved_by_name: string | null;
}

/** A pin the salesperson has placed but not sent. Local state only (D5). */
export interface DraftPin {
  /** Client-side key, never an id the server knows. */
  key: string;
  line_id: string;
  x: number;
  y: number;
  w: number;
  h: number;
  body: string;
}

/** What `POST .../request-changes` carries. */
export interface ChangeRequestPayload {
  comments: {
    line_id: string | null;
    x: number | null;
    y: number | null;
    w: number | null;
    h: number | null;
    body: string;
  }[];
  note?: string;
}

// ---------------------------------------------------------------------------
// Geometry
// ---------------------------------------------------------------------------

/** CSS `mm` is 96px/inch by spec, the same constant the sheet renders at. */
const PX_PER_MM = 96 / 25.4;

/** One placed tag's box on screen, in scaled pixels from the sheet's corner. */
export interface TagRect {
  tagId: string;
  lineId: string;
  left: number;
  top: number;
  width: number;
  height: number;
}

/** Every tag drawn on one sheet, in the same pixel space the sheet renders in. */
export function tagRectsForSheet(
  doc: TagSheetDoc | null,
  sheetIndex: number,
  scale: number,
): TagRect[] {
  const sheet = doc?.sheets[sheetIndex];
  if (!sheet) return [];
  return sheet.tags.map((tag) => ({
    tagId: tag.id,
    lineId: tag.request_line_id,
    left: tag.x_mm * PX_PER_MM * scale,
    top: tag.y_mm * PX_PER_MM * scale,
    width: tag.width_mm * PX_PER_MM * scale,
    height: tag.height_mm * PX_PER_MM * scale,
  }));
}

/** Clamp to the tag box: a pin dragged past the edge belongs to the edge. */
export function clampFraction(value: number): number {
  return Math.min(1, Math.max(0, value));
}

/**
 * The number a pin wears.
 *
 * Sent comments are numbered in the order they were sent, and drafts continue
 * that sequence, so a rail entry and the marker on the sheet always say the
 * same thing - including in a second round, where the earlier round's numbers
 * stay put rather than renumbering under the reader.
 */
export function numberedPins(
  comments: ReviewComment[],
  drafts: DraftPin[],
): { commentNumbers: Map<string, number>; draftNumbers: Map<string, number> } {
  const commentNumbers = new Map<string, number>();
  const draftNumbers = new Map<string, number>();
  let next = 1;
  for (const comment of comments) {
    if (comment.line_id === null) continue; // general comments carry no marker
    commentNumbers.set(comment.id, next);
    next += 1;
  }
  for (const draft of drafts) {
    draftNumbers.set(draft.key, next);
    next += 1;
  }
  return { commentNumbers, draftNumbers };
}

/** Open = nobody has ticked it Done. What the counts and badges read. */
export function openComments(comments: ReviewComment[]): ReviewComment[] {
  return comments.filter((comment) => comment.resolved_at === null);
}

/** Open pin count per line, for the designer's LINES rail badge (D6). */
export function openCountByLine(comments: ReviewComment[]): Map<string, number> {
  const counts = new Map<string, number>();
  for (const comment of openComments(comments)) {
    if (!comment.line_id) continue;
    counts.set(comment.line_id, (counts.get(comment.line_id) ?? 0) + 1);
  }
  return counts;
}

/**
 * One marker the designer canvas draws over the artboard (D6).
 *
 * The canvas edits ONE line's tag, and the artboard IS that tag's box, so a
 * comment's fractions map straight onto it with no sheet geometry in between.
 */
export interface CanvasReviewPin {
  id: string;
  number: number;
  x: number;
  y: number;
  w: number;
  h: number;
  body: string;
  resolved: boolean;
  caption: string;
}

/** This line's pinned comments, numbered the same way every other surface numbers them. */
export function canvasPinsForLine(
  comments: ReviewComment[],
  lineId: string | null,
): CanvasReviewPin[] {
  if (!lineId) return [];
  const { commentNumbers } = numberedPins(comments, []);
  return comments
    .filter(
      (comment) =>
        comment.line_id === lineId && comment.x !== null && comment.y !== null,
    )
    .map((comment) => ({
      id: comment.id,
      number: commentNumbers.get(comment.id) ?? 0,
      x: comment.x as number,
      y: comment.y as number,
      w: comment.w ?? 0,
      h: comment.h ?? 0,
      body: comment.body,
      resolved: comment.resolved_at !== null,
      caption: comment.resolved_at
        ? `Round ${comment.round} / Done`
        : `Round ${comment.round}`,
    }));
}

/** The highest round any comment carries, 0 when there are none. */
export function latestRound(comments: ReviewComment[]): number {
  return comments.reduce((max, comment) => Math.max(max, comment.round), 0);
}

// ---------------------------------------------------------------------------
// PHASE 1 MOCK - deleted when the routes above exist
// ---------------------------------------------------------------------------

/**
 * The in-memory stand-in for `price_tag_review_comments`.
 *
 * Phase 1 builds the whole review loop against this so every state (no pins,
 * one round, a second round over a resolved first, a general comment) can be
 * walked before a table exists - and so a Send on the lane's shared dev DB does
 * NOT transition the request the next slice still needs. Both service surfaces
 * (portal and CRM) read and write it, and each swaps its own body for a fetch
 * in Phase 2; nothing above the services knows which one is answering.
 */
const store = new Map<string, ReviewComment[]>();

let seq = 0;

export function mockListReviewComments(requestId: string): ReviewComment[] {
  return [...(store.get(requestId) ?? [])];
}

export function mockCreateReviewComments(
  requestId: string,
  payload: ChangeRequestPayload,
  author: string,
): ReviewComment[] {
  const existing = store.get(requestId) ?? [];
  const round = latestRound(existing) + 1;
  const now = new Date().toISOString();
  const created: ReviewComment[] = [];

  for (const comment of payload.comments) {
    seq += 1;
    created.push({
      id: `mock-comment-${seq}`,
      request_id: requestId,
      line_id: comment.line_id,
      round,
      x: comment.x,
      y: comment.y,
      w: comment.w,
      h: comment.h,
      body: comment.body,
      author_name: author,
      created_at: now,
      resolved_at: null,
      resolved_by_name: null,
    });
  }

  if (payload.note?.trim()) {
    seq += 1;
    created.push({
      id: `mock-comment-${seq}`,
      request_id: requestId,
      line_id: null,
      round,
      x: null,
      y: null,
      w: null,
      h: null,
      body: payload.note.trim(),
      author_name: author,
      created_at: now,
      resolved_at: null,
      resolved_by_name: null,
    });
  }

  store.set(requestId, [...existing, ...created]);
  return created;
}

export function mockSetResolved(
  requestId: string,
  commentId: string,
  resolved: boolean,
  actor: string,
): ReviewComment | null {
  const rows = store.get(requestId) ?? [];
  let updated: ReviewComment | null = null;
  store.set(
    requestId,
    rows.map((row) => {
      if (row.id !== commentId) return row;
      updated = {
        ...row,
        resolved_at: resolved ? new Date().toISOString() : null,
        resolved_by_name: resolved ? actor : null,
      };
      return updated;
    }),
  );
  return updated;
}

/** Tests and a fresh walk start from nothing. */
export function _resetReviewCommentStore(): void {
  store.clear();
  seq = 0;
}

/**
 * The same three functions on `window`, for a Phase 1 browser walk.
 *
 * The store lives in one JS context, so pins sent on the portal cannot be seen
 * by a CRM tab; seeding from the console is what lets the marketing half of the
 * loop (the Done list, the canvas markers, the LINES badge) be walked before the
 * table exists. Goes away with the store.
 */
if (typeof window !== 'undefined') {
  (window as unknown as Record<string, unknown>).__ptagReviewMock = {
    seed: mockCreateReviewComments,
    list: mockListReviewComments,
    resolve: mockSetResolved,
    reset: _resetReviewCommentStore,
  };
}
