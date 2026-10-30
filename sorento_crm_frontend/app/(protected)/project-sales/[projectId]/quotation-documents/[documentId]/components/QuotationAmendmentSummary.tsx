'use client';

import * as React from 'react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
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
  suggestedOnly,
  onSuggestedOnly,
}: {
  request: QuotationAmendmentRequest;
  canApply: boolean;
  applying: boolean;
  onApply: () => void;
  /** The Lines grid shows only the lines with a suggestion. */
  suggestedOnly: boolean;
  onSuggestedOnly: (next: boolean) => void;
}) {
  const total = request.rows.length;
  const lines = new Set(request.rows.map((row) => row.line_id)).size;
  const decided = request.rows.filter(
    (row) => row.decision !== 'pending',
  ).length;
  const undecided = total - decided;
  const who = request.requester_name || 'The customer';
  // A touched scope already has a hand-made draft: Apply would refuse, so it is off and says why.
  const blocked = request.blocked_scopes ?? [];

  return (
    <div className="space-y-2 rounded-lg border border-border bg-muted/40 px-4 py-3 text-sm">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:gap-6">
        <div className="min-w-0">
          <p className="text-xs text-muted-foreground">
            {request.submitted_at
              ? `${who} · ${formatDateTimeInMalaysia(request.submitted_at)}`
              : who}
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
        <div className="flex flex-col items-start gap-2 sm:flex-row sm:items-center lg:ms-auto">
          <div className="flex items-center gap-2">
            <Checkbox
              id="quotation-amendment-suggested-only"
              checked={suggestedOnly}
              onCheckedChange={(next) => onSuggestedOnly(next === true)}
            />
            <Label
              htmlFor="quotation-amendment-suggested-only"
              className="text-xs"
            >
              Suggested lines only
            </Label>
          </div>
          <div className="flex flex-col items-start gap-1 lg:items-end">
            <Button
              type="button"
              size="sm"
              disabled={
                !canApply || blocked.length > 0 || undecided > 0 || applying
              }
              onClick={onApply}
            >
              {applying ? 'Applying...' : 'Apply decisions'}
            </Button>
            {blocked.length === 0 && undecided > 0 && (
              <p className="text-xs text-muted-foreground">
                {`Accept or reject ${undecided === 1 ? 'the last suggestion' : `${undecided} more suggestions`} to apply.`}
              </p>
            )}
          </div>
        </div>
      </div>
      {blocked.map((scope) => (
        <p
          key={scope.quotation_id}
          className="text-xs font-medium text-warning"
        >
          {`A revision is already open on ${scope.scope_label}; issue or discard it first.`}
        </p>
      ))}
    </div>
  );
}
