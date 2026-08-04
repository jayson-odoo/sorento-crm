'use client';

import * as React from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { formatDateInMalaysia } from '@/lib/helpers';
import { formatMyrExact } from '../../../components/POIntakeMoney';
import type { QuotationDocument } from '../../../../_shared/services/quotationDocumentService';

/**
 * The letterhead, laid out the way the customer reads it on the printed quotation: the refs
 * that get quoted back on the right, who it is to on the left, then the one line naming the job.
 *
 * Every field here is DERIVED - recipient from the project's party, subject from the project
 * title, ref from the numbering rule. The screen shows them rather than asking for them, which
 * is the point of the journey step: the salesperson confirms, they do not fill in a form.
 *
 * The sender block the prototype drew is not here: the document contract carries no sender, and
 * an invented one on screen would disagree with whatever the PDF template prints. It belongs to
 * the template, so it stays there.
 */
function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex gap-2 text-sm">
      <span className="w-20 shrink-0 text-muted-foreground">{label}</span>
      <span className="min-w-0 break-words font-medium">{value}</span>
    </div>
  );
}

function addressLines(address: string | null): string[] {
  if (!address) return [];
  return address
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
}

export function QuotationDocumentHeader({ document }: { document: QuotationDocument }) {
  const lines = addressLines(document.recipient_address_snapshot);
  // `formatDateInMalaysia` answers '' on anything it cannot read, and a blank where a date
  // belongs reads as a rendering fault rather than as "no date yet".
  const docDate = document.doc_date ? formatDateInMalaysia(document.doc_date) : '';

  return (
    <Card>
      <CardContent className="grid gap-6 py-5 md:grid-cols-2">
        <div className="min-w-0 space-y-1">
          <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            To
          </p>
          <p className="min-w-0 break-words text-sm font-medium">
            {document.recipient_name_snapshot ?? '-'}
          </p>
          {lines.length > 0 ? (
            lines.map((row) => (
              <p key={row} className="min-w-0 break-words text-sm text-muted-foreground">
                {row}
              </p>
            ))
          ) : (
            <p className="text-sm text-muted-foreground">-</p>
          )}
          <p className="min-w-0 break-words text-sm text-muted-foreground">
            {document.recipient_phone_snapshot ?? '-'}
          </p>
          <p className="mt-2 text-sm">
            <span className="text-muted-foreground">Attn: </span>
            <span className="font-medium">{document.attn_name ?? '-'}</span>
          </p>
        </div>

        <div className="min-w-0 space-y-2 md:justify-self-end md:text-left">
          <Field label="Our Ref" value={document.our_ref ?? document.document_no} />
          <Field label="Your Ref" value={document.your_ref ?? '-'} />
          <Field label="Date" value={docDate || '-'} />
          {/* The total belongs with the refs, not beside the buttons in the page header. It is a
              FACT about the document, the same kind as its date, and the client asked for it here.
              Up in the header it competed with the primary action for the eye. */}
          <div className="flex gap-2 border-t border-border pt-2 text-sm">
            <span className="w-20 shrink-0 text-muted-foreground">Total</span>
            <span className="font-semibold tabular-nums">
              {formatMyrExact(document.grand_total)}
            </span>
          </div>
        </div>

        <div className="border-t border-border pt-4 md:col-span-2">
          <p className="min-w-0 break-words text-sm font-semibold uppercase tracking-wide">
            {document.subject_title ?? '-'}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
