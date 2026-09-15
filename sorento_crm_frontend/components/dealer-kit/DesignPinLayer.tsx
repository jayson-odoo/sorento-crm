'use client';

/**
 * Pins on the design (r9 S2/D5-D6).
 *
 * There is no "Request changes" mode to turn on: on a design that is waiting
 * for the salesperson, a click on a tag IS the change request. The click drops
 * a point pin, a drag draws a box, and either opens the comment box straight
 * away; Escape or an empty comment throws it away again.
 *
 * The layer sits over the rendered sheet and reads the SAME geometry the sheet
 * drew with, so a pin is anchored to a fraction of its tag rather than to a
 * spot on the page - the whole reason re-arranging or zooming cannot move it
 * off the thing it was pointing at.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { Trash2, X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/utils';
import {
  clampFraction,
  numberedPins,
  tagRectsForSheet,
  type DraftPin,
  type ReviewComment,
} from '@/lib/dealer-kit/review-comments';
import type { TagSheetDoc } from '@/lib/dealer-kit/tag-template-types';

/** What a surface hands the layer. Absent = no pins, no placing. */
export interface DesignReview {
  /** Every comment sent so far, all rounds. */
  comments: ReviewComment[];
  /** Pins placed in this session and not sent yet. */
  drafts: DraftPin[];
  /** True while the design is waiting on this reader (portal, proof_ready). */
  canPlace?: boolean;
  /**
   * Which round the design is on (R2). Pins from an EARLIER round render grey
   * whether or not they were ticked Done: they were about a proof that has
   * since been redrawn, so reading them as live work on this one is wrong.
   */
  currentRound?: number;
  onPlace?: (pin: Omit<DraftPin, 'key'>) => void;
  onRemoveDraft?: (key: string) => void;
}

interface DesignPinLayerProps extends DesignReview {
  doc: TagSheetDoc | null;
  sheetIndex: number;
  scale: number;
}

/** A drag under this many pixels is a click, and a click is a point pin. */
const DRAG_THRESHOLD_PX = 4;

interface Placing {
  /** The REQUEST TAG the clicked copy draws - the anchor the pin is stored on. */
  requestTagId: string;
  /** The placed copy that was clicked, so the editor opens over THAT box. */
  tagId: string;
  /** Fractions of the tag box. */
  x: number;
  y: number;
  w: number;
  h: number;
  /** Where the pointer went down, in tag fractions, so a drag can go any way. */
  originX: number;
  originY: number;
  /** The tag rect it started in, for drawing while the pointer is down. */
  rect: { left: number; top: number; width: number; height: number };
  /** True once the pointer is up and the comment box is open. */
  editing: boolean;
}

export default function DesignPinLayer({
  doc,
  sheetIndex,
  scale,
  comments,
  drafts,
  canPlace = false,
  currentRound,
  onPlace,
  onRemoveDraft,
}: DesignPinLayerProps) {
  const [placing, setPlacing] = useState<Placing | null>(null);
  const [body, setBody] = useState('');
  const [openMarker, setOpenMarker] = useState<string | null>(null);
  const draggingRef = useRef<{
    startX: number;
    startY: number;
    /** The tag's box in CLIENT coordinates, so a drag that leaves it still
     *  measures against the tag it started on. */
    box: DOMRect;
  } | null>(null);

  const rects = tagRectsForSheet(doc, sheetIndex, scale);
  const { commentNumbers, draftNumbers } = numberedPins(comments, drafts);

  const discard = useCallback(() => {
    setPlacing(null);
    setBody('');
    draggingRef.current = null;
  }, []);

  const commit = useCallback(() => {
    const text = body.trim();
    if (!placing || !text) {
      discard();
      return;
    }
    onPlace?.({
      tag_id: placing.requestTagId,
      x: placing.x,
      y: placing.y,
      w: placing.w,
      h: placing.h,
      body: text,
    });
    discard();
  }, [body, placing, onPlace, discard]);

  const startPlacing = useCallback(
    (rect: (typeof rects)[number], event: React.PointerEvent<HTMLDivElement>) => {
      if (!canPlace) return;
      // The lightbox pans on a drag; a drag that starts on a tag is drawing a
      // box, not moving the page.
      event.stopPropagation();
      event.preventDefault();
      const box = event.currentTarget.getBoundingClientRect();
      const x = clampFraction((event.clientX - box.left) / box.width);
      const y = clampFraction((event.clientY - box.top) / box.height);
      draggingRef.current = { startX: event.clientX, startY: event.clientY, box };
      setOpenMarker(null);
      setBody('');
      setPlacing({
        requestTagId: rect.requestTagId,
        tagId: rect.tagId,
        x,
        y,
        w: 0,
        h: 0,
        originX: x,
        originY: y,
        rect: { left: rect.left, top: rect.top, width: rect.width, height: rect.height },
        editing: false,
      });
    },
    [canPlace],
  );

  const endPlacing = useCallback(() => {
    draggingRef.current = null;
    setPlacing((current) => (current ? { ...current, editing: true } : current));
  }, []);

  // A drag that ENDS off the tag still finishes the pin. The move and up
  // handlers used to sit on the tag's own hit area, and a box around the whole
  // tag always leaves it (a fast drag usually does too), so the pointerup
  // never arrived: no box, no comment box, and the next click started again.
  // The window is where a drag actually lives - pointer capture is the
  // browser's own answer to this and jsdom does not implement it, so the
  // listeners would be untestable.
  const isPlacing = placing !== null && !placing.editing;
  useEffect(() => {
    if (!isPlacing) return;
    const onMove = (event: PointerEvent) => {
      const from = draggingRef.current;
      if (!from) return;
      const travelled =
        Math.abs(event.clientX - from.startX) + Math.abs(event.clientY - from.startY);
      if (travelled < DRAG_THRESHOLD_PX) return;
      const x = clampFraction((event.clientX - from.box.left) / from.box.width);
      const y = clampFraction((event.clientY - from.box.top) / from.box.height);
      setPlacing((current) =>
        current && !current.editing
          ? {
              ...current,
              // The pin sits at the box's corner (D5), so the anchor stays
              // where the pointer went down and the box grows either way.
              x: Math.min(current.originX, x),
              y: Math.min(current.originY, y),
              w: Math.abs(x - current.originX),
              h: Math.abs(y - current.originY),
            }
          : current,
      );
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', endPlacing);
    return () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', endPlacing);
    };
  }, [isPlacing, endPlacing]);

  if (!doc) return null;

  return (
    // The container never eats a pointer event: only the tag hit areas and the
    // markers do, so the lightbox can still pan and scroll everywhere else.
    <div className="pointer-events-none absolute inset-0" data-testid="design-pin-layer">
      {canPlace &&
        rects.map((rect) => (
          <div
            key={`hit-${rect.tagId}`}
            role="presentation"
            data-testid={`pin-hit-${rect.requestTagId}`}
            className="pointer-events-auto absolute cursor-crosshair hover:ring-1 hover:ring-primary/40"
            style={{
              left: rect.left,
              top: rect.top,
              width: rect.width,
              height: rect.height,
            }}
            onPointerDown={(event) => startPlacing(rect, event)}
          />
        ))}

      {/* Sent pins. The anchor is the request TAG, and every copy of one tag on
          the sheet (a quantity > 1) draws the same artwork - so the marker goes
          on all of them rather than on one copy chosen arbitrarily. A line that
          prints two different options prints them as two TAGS, and a pin on one
          of those never appears on the other. */}
      {comments.map((comment) => {
        if (!comment.tag_id || comment.x === null || comment.y === null) return null;
        const number = commentNumbers.get(comment.id);
        const targetRects = rects.filter(
          (rect) => rect.requestTagId === comment.tag_id,
        );
        return targetRects.map((rect) => (
            <PinMarker
              key={`${comment.id}-${rect.tagId}`}
              testId={`pin-${comment.id}`}
              number={number ?? 0}
              rect={rect}
              x={comment.x as number}
              y={comment.y as number}
              w={comment.w ?? 0}
              h={comment.h ?? 0}
              tone={
                comment.resolved_at ||
                (currentRound !== undefined && comment.round < currentRound)
                  ? 'resolved'
                  : 'sent'
              }
              open={openMarker === `${comment.id}-${rect.tagId}`}
              onToggle={() =>
                setOpenMarker((current) =>
                  current === `${comment.id}-${rect.tagId}`
                    ? null
                    : `${comment.id}-${rect.tagId}`,
                )
              }
              body={comment.body}
              caption={
                comment.resolved_at
                  ? `Round ${comment.round} · Done`
                  : `Round ${comment.round}`
              }
            />
          ));
      })}

      {/* Pins placed in this session, not sent yet. */}
      {drafts.map((draft) =>
        rects
          .filter((rect) => rect.requestTagId === draft.tag_id)
          .map((rect) => (
            <PinMarker
              key={`${draft.key}-${rect.tagId}`}
              testId={`draft-pin-${draft.key}`}
              number={draftNumbers.get(draft.key) ?? 0}
              rect={rect}
              x={draft.x}
              y={draft.y}
              w={draft.w}
              h={draft.h}
              tone="draft"
              open={openMarker === `${draft.key}-${rect.tagId}`}
              onToggle={() =>
                setOpenMarker((current) =>
                  current === `${draft.key}-${rect.tagId}`
                    ? null
                    : `${draft.key}-${rect.tagId}`,
                )
              }
              body={draft.body}
              caption="Not sent yet"
              onDelete={onRemoveDraft ? () => onRemoveDraft(draft.key) : undefined}
            />
          )),
      )}

      {/* The pin being placed: its box while the pointer is down, its comment
          box once it is up. */}
      {placing && (
        <>
          {placing.w > 0 && placing.h > 0 && (
            <div
              className="pointer-events-none absolute rounded-sm border-2 border-primary bg-primary/10"
              style={{
                left: placing.rect.left + placing.x * placing.rect.width,
                top: placing.rect.top + placing.y * placing.rect.height,
                width: placing.w * placing.rect.width,
                height: placing.h * placing.rect.height,
              }}
            />
          )}
          <div
            className="pointer-events-none absolute size-5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-background bg-primary"
            style={{
              left: placing.rect.left + placing.x * placing.rect.width,
              top: placing.rect.top + placing.y * placing.rect.height,
            }}
          />
          {placing.editing && (
            <div
              data-testid="pin-comment-editor"
              className="pointer-events-auto absolute z-10 w-56 rounded-lg border bg-popover p-2 shadow-md"
              style={{
                left: Math.max(
                  0,
                  placing.rect.left + placing.x * placing.rect.width - 112,
                ),
                top:
                  placing.rect.top +
                  (placing.y + placing.h) * placing.rect.height +
                  12,
              }}
            >
              <Textarea
                autoFocus
                rows={3}
                value={body}
                placeholder="What needs to change here?"
                onChange={(event) => setBody(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Escape') {
                    // Not the lightbox's Escape: this one throws the pin away
                    // and leaves the design open.
                    event.stopPropagation();
                    event.preventDefault();
                    discard();
                  }
                }}
                className="text-xs"
              />
              <div className="mt-2 flex justify-end gap-2">
                <Button variant="ghost" size="sm" onClick={discard}>
                  Cancel
                </Button>
                <Button size="sm" disabled={!body.trim()} onClick={commit}>
                  Add
                </Button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function PinMarker({
  testId,
  number,
  rect,
  x,
  y,
  w,
  h,
  tone,
  open,
  onToggle,
  body,
  caption,
  onDelete,
}: {
  testId: string;
  number: number;
  rect: { left: number; top: number; width: number; height: number };
  x: number;
  y: number;
  w: number;
  h: number;
  /** draft = not sent, sent = open on the current design, resolved = ticked Done. */
  tone: 'draft' | 'sent' | 'resolved';
  open: boolean;
  onToggle: () => void;
  body: string;
  caption: string;
  onDelete?: () => void;
}) {
  const left = rect.left + x * rect.width;
  const top = rect.top + y * rect.height;
  return (
    <>
      {w > 0 && h > 0 && (
        <div
          className={cn(
            'pointer-events-none absolute rounded-sm border-2',
            tone === 'resolved'
              ? 'border-muted-foreground/40 bg-muted-foreground/10'
              : 'border-primary bg-primary/10',
          )}
          style={{ left, top, width: w * rect.width, height: h * rect.height }}
        />
      )}
      <button
        type="button"
        data-testid={testId}
        aria-label={`Change request ${number}`}
        onPointerDown={(event) => event.stopPropagation()}
        onClick={onToggle}
        className={cn(
          'pointer-events-auto absolute flex size-5 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border-2 border-background text-2xs font-semibold text-white shadow',
          tone === 'resolved' ? 'bg-muted-foreground/60' : 'bg-primary',
          tone === 'draft' && 'ring-2 ring-primary/30',
        )}
        style={{ left, top }}
      >
        {number}
      </button>
      {open && (
        <div
          className="pointer-events-auto absolute z-10 w-56 rounded-lg border bg-popover p-2 text-xs shadow-md"
          style={{ left: Math.max(0, left - 112), top: top + 14 }}
          onPointerDown={(event) => event.stopPropagation()}
        >
          <div className="flex items-start justify-between gap-2">
            <span className="text-2xs uppercase tracking-wide text-muted-foreground">
              {caption}
            </span>
            <button
              type="button"
              aria-label="Close comment"
              className="text-muted-foreground hover:text-foreground"
              onClick={onToggle}
            >
              <X className="size-3.5" />
            </button>
          </div>
          <p className="mt-1 whitespace-pre-wrap">{body}</p>
          {onDelete && (
            <div className="mt-2 flex justify-end">
              <Button
                variant="ghost"
                size="sm"
                className="text-destructive hover:text-destructive"
                onClick={onDelete}
              >
                <Trash2 className="size-3.5 mr-1" />
                Delete
              </Button>
            </div>
          )}
        </div>
      )}
    </>
  );
}
