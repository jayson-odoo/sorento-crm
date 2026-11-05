'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { formatMyrExact, formatQty } from '../../../../_shared/lib/money';
import {
  useQuotationFeedback,
  useQuotationFeedbackMutation,
} from '../../../../_shared/hooks/useQuotationDocuments';
import type {
  QuotationFeedbackRequest,
  QuotationFeedbackRow,
} from '../../../../_shared/types/project.types';
import { useQuotationDocumentScreen } from './QuotationDocumentContext';

/** Where a note points: the scope, then the cell or the whole item. */
export function feedbackWhere(row: QuotationFeedbackRow): string {
  const at = row.cell_key
    ? (row.cell_label ?? '(column removed)')
    : 'whole item';
  return [row.scope_label, at].filter(Boolean).join(' · ');
}

/** The customer's optional hint, beside today's value. Null for a plain note. */
export function feedbackHint(row: QuotationFeedbackRow): string | null {
  switch (row.kind) {
    case 'quantity':
      return row.value_to
        ? `Suggested quantity ${formatQty(row.value_to)}${row.value_from ? ` (now ${formatQty(row.value_from)})` : ''}`
        : null;
    case 'unit_price':
      return row.value_to
        ? `Suggested price ${formatMyrExact(row.value_to)}${row.value_from ? ` (now ${formatMyrExact(row.value_from).replace(/^RM /, '')})` : ''}`
        : null;
    case 'remove':
      return 'Remove this item';
    case 'model_swap':
      return `Another model: ${row.model ?? '-'}${row.value_to ? ` at ${formatMyrExact(row.value_to)}` : ''}`;
    default:
      return null;
  }
}

function FeedbackRowCard({
  row,
  canEdit,
  onHandled,
  onShow,
}: {
  row: QuotationFeedbackRow;
  canEdit: boolean;
  onHandled: (handled: boolean) => void;
  onShow: () => void;
}) {
  const handled = Boolean(row.handled_at);
  const hint = feedbackHint(row);
  const id = `quotation-feedback-${row.id}`;
  return (
    <li
      data-testid="quotation-feedback-row"
      data-handled={handled ? 'true' : undefined}
      className={cn(
        'rounded-lg border border-border bg-background px-3 py-2.5',
        handled && 'opacity-60',
      )}
    >
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <span className="break-words font-medium">{row.line_description || 'Item'}</span>{' '}
          <span className="break-words text-xs text-muted-foreground">{feedbackWhere(row)}</span>
        </div>
        <div className="flex shrink-0 items-center gap-2 text-xs">
          <Checkbox
            id={id}
            checked={handled}
            disabled={!canEdit}
            onCheckedChange={(next) => onHandled(next === true)}
          />
          <label htmlFor={id} className="text-muted-foreground">
            {handled
              ? `Handled${row.handled_by_name ? ` by ${row.handled_by_name}` : ''}${
                  row.handled_at ? `, ${formatDateTimeInMalaysia(row.handled_at)}` : ''
                }`
              : 'Handled'}
          </label>
        </div>
      </div>
      {row.note && (
        <p className="mt-1 whitespace-pre-line break-words text-sm">{`"${row.note}"`}</p>
      )}
      <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
        {hint && <span className="break-words">{hint}</span>}
        <Button type="button" variant="ghost" size="sm" className="h-auto p-0 text-primary" onClick={onShow}>
          Show in Lines
        </Button>
      </div>
    </li>
  );
}

function RequestBlock({
  request,
  canEdit,
  onHandled,
  onShow,
}: {
  request: QuotationFeedbackRequest;
  canEdit: boolean;
  onHandled: (row: QuotationFeedbackRow, handled: boolean) => void;
  onShow: (row: QuotationFeedbackRow) => void;
}) {
  const from = [
    request.requester_name ? `From ${request.requester_name}` : 'From the customer',
    request.issue_label ? `on ${request.issue_label}` : null,
  ]
    .filter(Boolean)
    .join(' ');
  return (
    <section className="space-y-2">
      <p className="text-xs text-muted-foreground">
        {request.submitted_at ? `${from}, ${formatDateTimeInMalaysia(request.submitted_at)}` : from}
      </p>
      {request.note && (
        <blockquote className="whitespace-pre-line break-words rounded-md border border-border bg-muted/40 p-3 text-sm">
          {request.note}
        </blockquote>
      )}
      {request.rows.length > 0 && (
        <ul className="space-y-2">
          {request.rows.map((row) => (
            <FeedbackRowCard
              key={row.id}
              row={row}
              canEdit={canEdit}
              onHandled={(handled) => onHandled(row, handled)}
              onShow={() => onShow(row)}
            />
          ))}
        </ul>
      )}
    </section>
  );
}

/**
 * The Customer feedback tab (PS-QUOTE-MATRIX R20, mock v3 frame 5): every note the customer left
 * on the sign link, newest first, each with where it points, the hint beside today's value, and
 * Show in Lines. The one action is Handled (who and when recorded; unticking reopens). Nothing
 * here accepts, rejects or applies anything: the salesperson acts by editing a revision.
 */
export function QuotationFeedbackPanel() {
  const { projectId, documentId, document: record, canEdit, selectScope } =
    useQuotationDocumentScreen();
  const router = useRouter();
  const feedback = useQuotationFeedback(projectId, documentId);
  const handled = useQuotationFeedbackMutation(projectId, documentId);

  const show = (row: QuotationFeedbackRow) => {
    // By id when the row carries one (two scopes may share a label), by label otherwise. The
    // Lines tab opens the scope on its current version, where the notes are marked.
    const scopes = record.scopes ?? [];
    const scope =
      (row.scope_id ? scopes.find((item) => item.id === row.scope_id) : undefined) ??
      scopes.find((item) => item.scope_label === row.scope_label);
    if (scope) selectScope(scope.id);
    router.push(`/project-sales/${projectId}/quotation-documents/${documentId}`);
  };

  if (feedback.isLoading) return <Skeleton className="h-48 w-full" />;

  if (feedback.isError) {
    return (
      <Card>
        <CardContent className="px-6 py-10 text-center" role="alert">
          <h3 className="text-sm font-semibold">The customer feedback could not be loaded</h3>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
            {feedback.error instanceof Error && feedback.error.message
              ? feedback.error.message
              : 'Reload the page to try again.'}
          </p>
        </CardContent>
      </Card>
    );
  }

  const requests = feedback.data?.requests ?? [];
  if (requests.length === 0) {
    return (
      <Card>
        <CardContent className="px-6 py-10 text-center">
          <h3 className="text-sm font-semibold">No customer feedback yet</h3>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
            Nothing has come in from the sign link.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent className="space-y-6 py-5">
        {requests.map((request) => (
          <RequestBlock
            key={request.id}
            request={request}
            canEdit={canEdit}
            onHandled={(row, next) => handled.mutate({ rowId: row.id, handled: next })}
            onShow={show}
          />
        ))}
      </CardContent>
    </Card>
  );
}
