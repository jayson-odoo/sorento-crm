/**
 * Pinned change requests on a tag sheet design (r9 S2/D4-D6).
 *
 * A salesperson does not describe a change, they point at it: a click on the
 * tag drops a pin, a drag draws a box, and the comment hangs off that spot. The
 * anchor is stored as FRACTIONS of the tag's own box, not page millimetres, so
 * re-arranging the sheet, paging, or zooming leaves every pin exactly on the
 * part of the tag it was put on.
 *
 * ## API contract
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
  /**
   * The ONE placed copy of the tag this pin was clicked on, when a sheet
   * prints the same line more than once (a quantity > 1, or "Apply to all
   * lines"). Null on a general comment, a legacy pin sent before this field
   * existed, or a copy the sheet no longer carries - any of those falls back
   * to drawing on every copy of the line. Optional (not just nullable) so a
   * pre-r9 caller that has not been told about it yet still type-checks.
   */
  placed_tag_id?: string | null;
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
  /** The placed copy that was clicked, or null when the line has only one. */
  placed_tag_id?: string | null;
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
    placed_tag_id?: string | null;
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

/**
 * This line's pinned comments, numbered the same way every other surface
 * numbers them.
 *
 * `placedTagId` is the ONE copy the canvas has open (the artboard IS that
 * `PlacedTag`, owner round finding 1): when given, a pin anchored to a
 * DIFFERENT copy of this line is left out, and a pin with no copy of its own
 * (null - a general fallback or a legacy pin) still comes back, the same
 * fallback `DesignPinLayer` draws on the sheet.
 */
export function canvasPinsForLine(
  comments: ReviewComment[],
  lineId: string | null,
  placedTagId?: string | null,
): CanvasReviewPin[] {
  if (!lineId) return [];
  const { commentNumbers } = numberedPins(comments, []);
  return comments
    .filter(
      (comment) =>
        comment.line_id === lineId &&
        comment.x !== null &&
        comment.y !== null &&
        (!placedTagId ||
          !comment.placed_tag_id ||
          comment.placed_tag_id === placedTagId),
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
