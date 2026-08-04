'use client';

import * as React from 'react';
import { formatDateInMalaysia } from '@/lib/helpers';
import { Card, CardContent } from '@/components/ui/card';
import { formatMyr } from '../../components/QuotationsPanel';
import type { MockDocument } from './documentMocks';

/**
 * The letterhead, laid out the way the customer reads it on the printed quotation:
 * who it is from on the left, the refs that get quoted back on the right, then who it
 * is to, then the one line naming the job.
 *
 * Every field here is DERIVED (AC-A2) - company from the tenant, recipient from the
 * project's party, subject from the project title, ref from the numbering rule. The
 * screen shows them rather than asking for them, which is the whole point of the
 * journey step: the salesperson confirms, they do not fill in a form.
 */
function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex gap-2 text-sm">
      <span className="w-20 shrink-0 text-muted-foreground">{label}</span>
      <span className="min-w-0 break-words font-medium">{value ?? '-'}</span>
    </div>
  );
}

export function QuotationDocumentHeader({
  document,
  grandTotal,
}: {
  document: MockDocument;
  grandTotal: number;
}) {
  const ourRef = document.issue_label
    ? `${document.document_no} (${document.issue_label})`
    : document.document_no;

  return (
    <Card>
      <CardContent className="grid gap-6 py-5 md:grid-cols-2">
        <div className="space-y-4">
          <div>
            <p className="text-sm font-semibold">{document.sender.name}</p>
            {document.sender.lines.map((row) => (
              <p key={row} className="text-sm text-muted-foreground">
                {row}
              </p>
            ))}
            <p className="text-sm text-muted-foreground">Tel: {document.sender.tel}</p>
          </div>

          <div className="border-t border-border pt-4">
            <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              To
            </p>
            <p className="text-sm font-medium">{document.recipient.name}</p>
            {document.recipient.lines.map((row) => (
              <p key={row} className="text-sm text-muted-foreground">
                {row}
              </p>
            ))}
            {document.recipient.phones.map((row) => (
              <p key={row} className="text-sm text-muted-foreground">
                {row}
              </p>
            ))}
            <p className="mt-2 text-sm">
              <span className="text-muted-foreground">Attn: </span>
              <span className="font-medium">{document.attn_name ?? '-'}</span>
            </p>
          </div>
        </div>

        <div className="space-y-2 md:justify-self-end md:text-left">
          <Field label="Our Ref" value={ourRef} />
          <Field label="Your Ref" value={document.your_ref ?? '-'} />
          <Field label="Date" value={formatDateInMalaysia(document.doc_date)} />
          {/* The total belongs with the refs, not beside the buttons in the page header. It is a
              FACT about the document, the same kind as its date, and the client asked for it here.
              Up in the header it competed with the primary action for the eye. */}
          <div className="flex gap-2 border-t border-border pt-2 text-sm">
            <span className="w-20 shrink-0 text-muted-foreground">Total</span>
            <span className="font-semibold tabular-nums">{formatMyr(String(grandTotal))}</span>
          </div>
        </div>

        <div className="md:col-span-2 border-t border-border pt-4">
          <p className="text-sm font-semibold uppercase tracking-wide">
            {document.subject_title}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
