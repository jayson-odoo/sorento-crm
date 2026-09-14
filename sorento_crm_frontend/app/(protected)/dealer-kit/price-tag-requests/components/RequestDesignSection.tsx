'use client';

/**
 * The design, at the top of the CRM Request tab (r9 S1/D3), with the
 * salesperson's pinned change requests over it (r9 S2/D6).
 *
 * Marketing used to have to open the designer to see what a request looks like,
 * which meant loading the whole Konva editor to answer "is this the one the
 * salesperson is asking about". The same `DesignViewer` the portal reads is the
 * answer, drawing the DRAFT (B1) so the office sees its own work in progress -
 * and the same pins the salesperson placed, each with a Done toggle, so a round
 * of changes is worked off one list rather than a paragraph of prose.
 */

import { useCallback, useEffect, useState } from 'react';
import { Check, Undo2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { toast } from '@/lib/toast';
import { cn } from '@/lib/utils';
import DesignViewer from '@/components/dealer-kit/DesignViewer';
import { getRequestDesignPayload } from '../../services/priceTagRequestService';
import {
  listReviewComments,
  setReviewCommentResolved,
} from '../../services/priceTagReviewService';
import { numberedPins, type ReviewComment } from '@/lib/dealer-kit/review-comments';
import type { TagSheetDesignPayload } from '@/lib/dealer-kit/design-payload';

interface Props {
  requestId: string;
  docNumber: string;
  /** Line id -> what to call it, so no id reaches the screen. */
  lineLabels: Map<string, string>;
  /** The page keeps the open count for the primary CTA's label (D6). */
  onCommentsChange?: (comments: ReviewComment[]) => void;
}

export default function RequestDesignSection({
  requestId,
  docNumber,
  lineLabels,
  onCommentsChange,
}: Props) {
  const [payload, setPayload] = useState<TagSheetDesignPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [comments, setComments] = useState<ReviewComment[]>([]);
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getRequestDesignPayload(requestId)
      .then((data) => {
        if (!cancelled) setPayload(data);
      })
      .catch(() => {
        // No design yet, or the fetch failed - the empty state is the right
        // answer either way, and the page has nothing else to say about it.
        if (!cancelled) setPayload(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [requestId]);

  const publish = useCallback(
    (rows: ReviewComment[]) => {
      setComments(rows);
      onCommentsChange?.(rows);
    },
    [onCommentsChange],
  );

  useEffect(() => {
    let cancelled = false;
    listReviewComments(requestId)
      .then((rows) => {
        if (!cancelled) publish(rows);
      })
      .catch(() => {
        // The design still renders without its comments.
      });
    return () => {
      cancelled = true;
    };
  }, [requestId, publish]);

  const toggleResolved = useCallback(
    async (comment: ReviewComment) => {
      setBusyId(comment.id);
      try {
        await setReviewCommentResolved(
          requestId,
          comment.id,
          comment.resolved_at === null,
        );
        publish(await listReviewComments(requestId));
      } catch {
        toast.error('Could not update the change request');
      } finally {
        setBusyId(null);
      }
    },
    [requestId, publish],
  );

  const { commentNumbers } = numberedPins(comments, []);

  const footer =
    comments.length > 0 ? (
      <div className="mt-3 space-y-2 border-t pt-3">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Change requests
        </p>
        {comments.map((comment) => {
          const done = comment.resolved_at !== null;
          return (
            <div
              key={comment.id}
              className="flex items-start gap-2 rounded-md border p-2"
            >
              <span
                className={cn(
                  'mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full text-2xs font-semibold text-white',
                  done ? 'bg-muted-foreground/60' : 'bg-primary',
                )}
              >
                {comment.line_id ? (commentNumbers.get(comment.id) ?? '-') : '-'}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-2xs uppercase tracking-wide text-muted-foreground">
                  {comment.line_id
                    ? (lineLabels.get(comment.line_id) ?? 'Tag')
                    : 'General'}
                  {' / round '}
                  {comment.round}
                  {comment.author_name ? ` / ${comment.author_name}` : ''}
                </p>
                <p
                  className={cn(
                    'whitespace-pre-wrap text-sm',
                    done && 'text-muted-foreground line-through',
                  )}
                >
                  {comment.body}
                </p>
              </div>
              <Button
                variant={done ? 'ghost' : 'outline'}
                size="sm"
                disabled={busyId === comment.id}
                onClick={() => void toggleResolved(comment)}
              >
                {done ? (
                  <>
                    <Undo2 className="size-3.5 mr-1" />
                    Reopen
                  </>
                ) : (
                  <>
                    <Check className="size-3.5 mr-1" />
                    Done
                  </>
                )}
              </Button>
            </div>
          );
        })}
      </div>
    ) : null;

  return (
    <DesignViewer
      docNumber={docNumber}
      payload={payload}
      loading={loading}
      emptyMessage="No design yet"
      emptyHint="Claim the request and open the designer to draw the tags."
      review={{ comments, drafts: [] }}
      footer={footer}
    />
  );
}
