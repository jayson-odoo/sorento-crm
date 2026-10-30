'use client';

/**
 * The salesperson's proof review (D11, r9 S1/D2-D5): the request's real tag sheet design through
 * the shared `DesignViewer`, pins placed on it, the numbered rail of pins not sent yet, a general
 * note, Send (one call for the round) and Approve beside the design.
 *
 * Shared by the portal's price tag form and the CRM request page a salesperson reviews their own
 * proof on (PORTAL-P4-REQUESTS S7b). The caller injects where the design and the earlier rounds are
 * read from (the portal token, or `/api/v1/my-requests`); pass stable functions, the reads re-run
 * when they change. Moved out of `app/(auth)/portal/components/PriceTagRequestForm.tsx` unchanged.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { Check, Loader2, MessageSquare, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import DesignViewer from '@/components/dealer-kit/DesignViewer';
import type { DesignDownload } from '@/components/dealer-kit/DesignLightbox';
import {
  numberedPins,
  type ChangeRequestPayload,
  type DraftPin,
  type ReviewComment,
} from '@/lib/dealer-kit/review-comments';
import type { TagSheetDesignPayload } from '@/lib/dealer-kit/design-payload';
import { cn } from '@/lib/utils';

/** What the review reads off the request: never more than the portal's own detail body carries. */
export interface PriceTagReviewRequest {
  id: string;
  doc_number?: string | null;
  /** Which review round the design is on (D4): pins from an earlier round render grey. */
  review_round?: number;
  lines: Array<{
    code: string;
    name: string;
    tags?: Array<{ id: string; label: string }> | null;
  }>;
}

interface PriceTagDesignReviewProps {
  request: PriceTagReviewRequest;
  /** The design is waiting on this reader: pins can be placed and sent. */
  reviewable: boolean;
  onApprove: () => void;
  onSend: (payload: ChangeRequestPayload) => Promise<void>;
  download?: DesignDownload;
  /** The request's design, or null while there is none to show. */
  loadDesign: (id: string) => Promise<TagSheetDesignPayload | null>;
  /** Every change request sent on this design, all rounds. */
  loadReviewComments: (id: string) => Promise<ReviewComment[]>;
}

/**
 * Fetches the request's real tag sheet design and renders it through the
 * shared `DesignViewer` - the same `TagSheetRenderer` the CRM detail page and
 * the PDF export draw with, now fed the artwork and brand fonts as well, so
 * what the salesperson reviews here is what gets printed.
 *
 * First section on the page from `proof_ready` onward (D3): the design is what
 * the salesperson opened the request to look at, and everything above it was
 * scrolling past their own answers to reach it.
 */
export function PriceTagDesignReview({
  request,
  reviewable,
  onApprove,
  onSend,
  download,
  loadDesign,
  loadReviewComments,
}: PriceTagDesignReviewProps) {
  const [payload, setPayload] = useState<TagSheetDesignPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [comments, setComments] = useState<ReviewComment[]>([]);
  const [drafts, setDrafts] = useState<DraftPin[]>([]);
  const [generalNote, setGeneralNote] = useState('');
  const [sending, setSending] = useState(false);
  /** The footer rail: scrolled into view once, when the FIRST pin lands, so
   *  the salesperson sees `Send N change requests` appear without hunting
   *  for it - a later pin lands where they already are and must not yank
   *  the page again. */
  const railRef = useRef<HTMLDivElement | null>(null);
  const railScrolledRef = useRef(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    loadDesign(request.id)
      .then((data) => {
        if (!cancelled) setPayload(data);
      })
      .catch(() => {
        if (!cancelled) setPayload(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [request.id, loadDesign]);

  useEffect(() => {
    let cancelled = false;
    loadReviewComments(request.id)
      .then((rows) => {
        if (!cancelled) setComments(rows);
      })
      .catch(() => {
        // A design that will not tell us its history still has to render.
      });
    return () => {
      cancelled = true;
    };
  }, [request.id, loadReviewComments]);

  useEffect(() => {
    if (drafts.length > 0 && !railScrolledRef.current) {
      railScrolledRef.current = true;
      railRef.current?.scrollIntoView({ block: 'nearest' });
    }
  }, [drafts.length]);

  const { commentNumbers, draftNumbers } = numberedPins(comments, drafts);
  /**
   * What a pin's rail entry calls the thing it points at, never an id.
   *
   * The line's code, plus the tag's own label when the line prints more than
   * one ("SRT-1234 1b"): a line split into an option per basin shows two tags,
   * and a pin on one of them has to say which.
   */
  const tagLabel = useCallback(
    (tagId: string | null) => {
      if (!tagId) return 'General';
      for (const line of request.lines) {
        const tags = line.tags ?? [];
        const tag = tags.find((row) => row.id === tagId);
        if (!tag) continue;
        const code = line.code || line.name || 'Tag';
        return tags.length > 1 ? `${code} ${tag.label}` : code;
      }
      return 'Tag';
    },
    [request.lines],
  );

  const send = useCallback(async () => {
    if (drafts.length === 0 && !generalNote.trim()) return;
    setSending(true);
    try {
      await onSend({
        comments: drafts.map((draft) => ({
          tag_id: draft.tag_id,
          x: draft.x,
          y: draft.y,
          w: draft.w,
          h: draft.h,
          body: draft.body,
        })),
        note: generalNote.trim() || undefined,
      });
      // Only a round the server took is a round to forget.
      setDrafts([]);
      setGeneralNote('');
    } catch {
      // The caller has already said so; the pins stay exactly where they were.
    } finally {
      setSending(false);
    }
  }, [drafts, generalNote, onSend]);

  // Earlier rounds stay on the design and render grey (D6/R2), so a second
  // round is read against what the first one said without being mistaken for
  // live work on this proof.
  const review = {
    comments,
    drafts,
    canPlace: reviewable,
    currentRound: request.review_round,
    onPlace: (pin: Omit<DraftPin, 'key'>) =>
      setDrafts((current) => [
        ...current,
        { ...pin, key: `draft-${Date.now()}-${current.length}` },
      ]),
    onRemoveDraft: (key: string) =>
      setDrafts((current) => current.filter((draft) => draft.key !== key)),
  };

  const sentThisDesign = comments.filter((comment) => comment.tag_id !== null);

  const footer = reviewable ? (
    <div ref={railRef} className="mt-3 space-y-3 border-t pt-3">
      {drafts.length > 0 && (
        <ul className="space-y-2">
          {drafts.map((draft) => (
            <li
              key={draft.key}
              className="flex items-start gap-2 rounded-md border p-2"
            >
              <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-primary text-2xs font-semibold text-white">
                {draftNumbers.get(draft.key)}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-2xs uppercase tracking-wide text-muted-foreground">
                  {tagLabel(draft.tag_id)}
                </p>
                <p className="whitespace-pre-wrap text-xs">{draft.body}</p>
              </div>
              <Button
                variant="ghost"
                size="sm"
                aria-label={`Delete change request ${draftNumbers.get(draft.key)}`}
                className="text-destructive hover:text-destructive"
                onClick={() =>
                  setDrafts((current) =>
                    current.filter((row) => row.key !== draft.key),
                  )
                }
              >
                <Trash2 className="size-3.5" />
              </Button>
            </li>
          ))}
        </ul>
      )}

      <div className="space-y-1.5">
        <Label htmlFor="ptag-general-note" className="text-xs">
          Anything else (optional)
        </Label>
        <Textarea
          id="ptag-general-note"
          rows={2}
          value={generalNote}
          onChange={(event) => setGeneralNote(event.target.value)}
          placeholder="A note about the whole design"
          className="text-sm"
        />
      </div>

      {(drafts.length > 0 || generalNote.trim()) && (
        <Button
          className="w-full"
          disabled={sending}
          onClick={() => void send()}
          data-testid="send-change-requests"
        >
          {sending ? (
            <Loader2 className="size-4 mr-1 animate-spin" />
          ) : (
            <MessageSquare className="size-4 mr-1" />
          )}
          {drafts.length === 0
            ? 'Send change request'
            : drafts.length === 1
              ? 'Send 1 change request'
              : `Send ${drafts.length} change requests`}
        </Button>
      )}
    </div>
  ) : sentThisDesign.length > 0 ? (
    <div className="mt-3 space-y-2 border-t pt-3">
      {sentThisDesign.map((comment) => (
        <div key={comment.id} className="flex items-start gap-2">
          <span
            className={cn(
              'mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full text-2xs font-semibold text-white',
              comment.resolved_at ? 'bg-muted-foreground/60' : 'bg-primary',
            )}
          >
            {commentNumbers.get(comment.id)}
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-2xs uppercase tracking-wide text-muted-foreground">
              {tagLabel(comment.tag_id)}
              {comment.resolved_at ? ' / Done' : ''}
            </p>
            <p className="whitespace-pre-wrap text-xs">{comment.body}</p>
          </div>
        </div>
      ))}
    </div>
  ) : null;

  return (
    <DesignViewer
      docNumber={request.doc_number ?? 'Design'}
      payload={payload}
      loading={loading}
      emptyMessage="Design not available yet"
      emptyHint="Marketing is still working on it."
      download={download}
      review={review}
      footer={footer}
      headerActions={
        reviewable ? (
          <Button size="sm" onClick={onApprove}>
            <Check className="size-4 mr-1" />
            Approve
          </Button>
        ) : undefined
      }
    />
  );
}
