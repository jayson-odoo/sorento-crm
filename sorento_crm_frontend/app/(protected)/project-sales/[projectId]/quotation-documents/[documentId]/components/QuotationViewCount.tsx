'use client';

import * as React from 'react';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { useQuotationViews } from '../../../../_shared/hooks/useQuotationDocuments';
import type { QuotationDocument } from '../../../../_shared/services/quotationDocumentService';

const DEVICE_LABEL: Record<string, string> = {
  mobile: 'Phone',
  tablet: 'Tablet',
  desktop: 'Computer',
};

/** "Viewed 3 times, last 02/11/2026, 9:41 pm" for the revision the customer holds now. */
export function viewCountText(
  document: Pick<QuotationDocument, 'view_count' | 'last_viewed_at'>,
) {
  const count = document.view_count ?? 0;
  if (count === 0 || !document.last_viewed_at) return 'Not viewed yet';
  const times = count === 1 ? '1 time' : `${count} times`;
  return `Viewed ${times}, last ${formatDateTimeInMalaysia(document.last_viewed_at)}`;
}

function ViewLog({
  projectId,
  documentId,
}: {
  projectId: string;
  documentId: string;
}) {
  const views = useQuotationViews(projectId, documentId);
  if (views.isLoading)
    return <p className="text-sm text-muted-foreground">Loading...</p>;
  if (views.isError)
    return <p className="text-sm text-destructive">{views.error.message}</p>;
  const rows = views.data ?? [];
  if (rows.length === 0) {
    return (
      <div>
        <p className="text-sm font-medium">No views yet</p>
        <p className="text-xs text-muted-foreground">
          Opens of the link by the customer appear here.
        </p>
      </div>
    );
  }
  return (
    <ul className="max-h-72 space-y-1.5 overflow-y-auto" aria-label="View log">
      {rows.map((row) => (
        <li
          key={row.id}
          className="flex flex-wrap items-baseline justify-between gap-x-3 text-sm"
        >
          <span>{formatDateTimeInMalaysia(row.viewed_at)}</span>
          <span className="text-muted-foreground">
            {row.our_ref} · {DEVICE_LABEL[row.device] ?? row.device}
          </span>
        </li>
      ))}
    </ul>
  );
}

/**
 * The customer's opens of the sign link (PS-QUOTE-VIEWS), as one line of read-only metadata under
 * the record header. Pressing it opens the view log: every revision, newest first. Nothing renders
 * before the first issue, because until then no link exists.
 */
export function QuotationViewCount({
  projectId,
  document,
}: {
  projectId: string;
  document: QuotationDocument;
}) {
  const [open, setOpen] = React.useState(false);
  if (!document.is_issued) return null;
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="text-left text-sm text-muted-foreground underline-offset-4 hover:underline"
          data-testid="quotation-view-count"
        >
          {viewCountText(document)}
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-[min(22rem,calc(100vw-2rem))]">
        <p className="mb-2 text-sm font-semibold">View log</p>
        {open && <ViewLog projectId={projectId} documentId={document.id} />}
      </PopoverContent>
    </Popover>
  );
}
