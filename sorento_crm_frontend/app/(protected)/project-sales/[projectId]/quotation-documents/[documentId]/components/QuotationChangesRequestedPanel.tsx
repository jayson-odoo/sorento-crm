'use client';

import * as React from 'react';
import { MessageSquareText, SquarePen } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { hasOpenChangeRequest } from '../../../../_shared/lib/quotationDecision';
import type { QuotationDocument } from '../../../../_shared/services/quotationDocumentService';

/**
 * The customer has asked for something, said on the document rather than behind a tab.
 *
 * The client sent a screenshot of their own request on the counter-sign page and asked "when i
 * request changes, how can i see it from the system?" - the question of somebody who went looking
 * and could not find it. It WAS recorded, on the Signatures tab, and a tab the salesperson has no
 * reason to open is not where "the customer is waiting on you" belongs.
 *
 * Same family as `QuotationApprovalPanel`: a strip directly under the page header that renders
 * NOTHING at all in the ordinary case, and when it does appear names the reason AND offers the
 * next action as a click. Two things are deliberate here:
 *
 * - **The customer's own words are the payload.** "They asked for changes" is a notification;
 *   what a salesperson acts on is "can you provide me more discount". Quoted verbatim, newlines
 *   kept, never truncated.
 * - **The button is the EXISTING revise entry point**, handed down by the shell. The system does
 *   not open a revision by itself (the salesperson decides), so this leads to the same prompt
 *   Edit does rather than being a second way to revise.
 *
 * Acceptance beats a request, and that ranking is the serializer's - read through
 * `hasOpenChangeRequest`, never re-derived from the timestamps, so this panel, the counter-sign
 * page and the Signatures badge cannot disagree about a quotation that was signed afterwards.
 */
export function QuotationChangesRequestedPanel({
  document,
  reviseLabel,
  onRevise,
  isRevising = false,
}: {
  document: QuotationDocument;
  /** What the click will actually do, e.g. "Revise to v3". */
  reviseLabel: string;
  /** Omitted for a reader, and while an edit session is already open. */
  onRevise?: () => void;
  isRevising?: boolean;
}) {
  if (!hasOpenChangeRequest(document)) return null;

  const who = document.changes_requested_by_name?.trim() || 'The customer';
  const when = document.changes_requested_at
    ? formatDateTimeInMalaysia(document.changes_requested_at)
    : null;
  const note = document.changes_requested_note?.trim() ?? '';

  return (
    <div className="rounded-lg border border-amber-500/40 bg-amber-500/5 px-4 py-3">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 gap-2.5">
          <MessageSquareText
            className="mt-0.5 size-4 shrink-0 text-amber-600"
            aria-hidden
          />
          <div className="min-w-0 space-y-2">
            <p className="min-w-0 break-words text-sm text-foreground">
              {when
                ? `${who} asked for changes on ${when}.`
                : `${who} asked for changes.`}
            </p>
            {note && (
              <blockquote className="min-w-0 whitespace-pre-line break-words rounded-md border border-border bg-background/60 p-3 text-sm">
                {note}
              </blockquote>
            )}
          </div>
        </div>

        {onRevise && (
          <div className="flex flex-wrap items-center gap-2 sm:justify-end">
            <Button type="button" size="sm" disabled={isRevising} onClick={onRevise}>
              <SquarePen className="size-4" aria-hidden />
              {reviseLabel}
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
