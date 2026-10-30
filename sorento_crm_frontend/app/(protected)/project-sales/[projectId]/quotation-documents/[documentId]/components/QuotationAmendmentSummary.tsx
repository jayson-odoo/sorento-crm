'use client';

import * as React from 'react';
import { Button } from '@/components/ui/button';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import type { QuotationAmendmentRequest } from '../../../../_shared/types/project.types';
import { formatMyrExact } from '../../../../_shared/lib/money';

/**
 * The one summary row above the Lines grid while the customer's suggestions are open
 * (QUOTE-CUSTOMER-AMEND, mock v3 section 5): who and when, the counts, the totals and Apply.
 * The suggestions themselves are decided in the grid's own cells, never here.
 */
export function QuotationAmendmentSummary({
  request,
  canApply,
  applying,
  onApply,
}: {
  request: QuotationAmendmentRequest;
  canApply: boolean;
  applying: boolean;
  onApply: () => void;
}) {
  const total = request.rows.length;
  const lines = new Set(request.rows.map((row) => row.line_id)).size;
  const decided = request.rows.filter((row) => row.decision !== 'pending').length;
  const undecided = total - decided;
  const who = request.requester_name || 'The customer';

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border bg-muted/40 px-4 py-3 text-sm lg:flex-row lg:items-center lg:gap-6">
      <div className="min-w-0">
        <p className="text-xs text-muted-foreground">
          {request.submitted_at ? `${who} · ${formatDateTimeInMalaysia(request.submitted_at)}` : who}
        </p>
        <p className="font-medium">
          {total === 0
            ? 'A note, no line changes'
            : `${total} ${total === 1 ? 'suggestion' : 'suggestions'} on ${lines} ${
                lines === 1 ? 'line' : 'lines'
              } · ${decided} decided`}
        </p>
      </div>
      <div className="min-w-0">
        <p className="text-xs text-muted-foreground">Total</p>
        <p className="font-medium tabular-nums">
          {`${formatMyrExact(request.total_issued)} → ${formatMyrExact(request.total_after)}`}
        </p>
      </div>
      {request.note && (
        <p className="min-w-0 break-words lg:max-w-sm" title={request.note}>
          <span className="text-muted-foreground">Note: </span>
          {`"${request.note}"`}
        </p>
      )}
      <div className="flex flex-col items-start gap-1 lg:ms-auto lg:items-end">
        <Button
          type="button"
          size="sm"
          disabled={!canApply || undecided > 0 || applying}
          onClick={onApply}
        >
          {applying ? 'Applying...' : 'Apply decisions'}
        </Button>
        {undecided > 0 && (
          <p className="text-xs text-muted-foreground">
            {`Accept or reject ${undecided === 1 ? 'the last suggestion' : `${undecided} more suggestions`} to apply.`}
          </p>
        )}
      </div>
    </div>
  );
}
