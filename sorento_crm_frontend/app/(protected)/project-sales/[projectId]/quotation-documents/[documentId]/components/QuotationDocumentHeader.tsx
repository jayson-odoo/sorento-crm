'use client';

import * as React from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { formatDateInMalaysia } from '@/lib/helpers';
import { formatMyrExact } from '../../../../_shared/lib/money';
import type {
  QuotationDocument,
  QuotationDocumentBody,
} from '../../../../_shared/services/quotationDocumentService';

/**
 * The letterhead, laid out the way the customer reads it on the printed quotation: the refs
 * that get quoted back on the right, who it is to on the left, then the one line naming the job.
 *
 * Every field here ARRIVES derived - recipient from the project's party, subject from the project
 * title, ref from the numbering rule. The screen shows them rather than asking for them, which
 * is the point of the journey step: the salesperson confirms, they do not fill in a form.
 *
 * Derived is not the same as fixed, though, and the client said so: "when we are in edit view
 * right, we need to be able to edit these also, like the header details, your ref, date, to,
 * attn". So in an edit session the same block becomes inputs onto the same values. The recipient
 * is still SNAPSHOTTED rather than re-derived - what an edit corrects is this quotation's copy
 * (the finance department's mailing address, say), never the party record behind it.
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

/**
 * The same field with a way in. Stacked label over control rather than beside it, because the
 * side-by-side read layout leaves an input about eighty pixels wide on a phone.
 */
function EditField({
  id,
  label,
  children,
}: {
  id: string;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="min-w-0 space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children}
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

export function QuotationDocumentHeader({
  document,
  liveGrandTotal = null,
  onChange,
}: {
  /**
   * The document as the screen currently stands: the shell hands down the server's row with the
   * staged header edits already merged over it, so one prop is both what to display and what an
   * input is currently holding.
   */
  document: QuotationDocument;
  /**
   * The total as the screen currently stands, including line edits the user has typed but not
   * yet saved. Optional and null by default: `document.grand_total` is the server's figure, and
   * it only moves on a refetch, so a header reading it alone sits still while the table under it
   * changes - the number the user is watching disagrees with the number they are editing.
   */
  liveGrandTotal?: string | null;
  /**
   * Set only in an edit session, exactly like the letter panels' own `onChange`. Absent means
   * this is a read. Typing here writes nothing: it stages onto the document draft, and the
   * screen's one Save sends it with the lines.
   */
  onChange?: (patch: QuotationDocumentBody) => void;
}) {
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
          {onChange ? (
            <div className="space-y-3 pt-1">
              <EditField id="quotation-recipient-name" label="Name">
                <Input
                  id="quotation-recipient-name"
                  value={document.recipient_name_snapshot ?? ''}
                  // Emptied means "this quotation names nobody", which is a null column rather
                  // than a blank string the PDF would print as a stray empty line.
                  onChange={(event) =>
                    onChange({ recipient_name_snapshot: event.target.value || null })
                  }
                  placeholder="Who the quotation is addressed to"
                />
              </EditField>
              {/* A textarea because the address IS multi-line: it is stored as one string and
                  printed a line per newline, so a single-line input would flatten it. */}
              <EditField id="quotation-recipient-address" label="Address">
                <Textarea
                  id="quotation-recipient-address"
                  rows={3}
                  value={document.recipient_address_snapshot ?? ''}
                  onChange={(event) =>
                    onChange({ recipient_address_snapshot: event.target.value || null })
                  }
                  placeholder="One line per line of the address"
                />
              </EditField>
              <EditField id="quotation-recipient-phone" label="Phone">
                <Input
                  id="quotation-recipient-phone"
                  value={document.recipient_phone_snapshot ?? ''}
                  onChange={(event) =>
                    onChange({ recipient_phone_snapshot: event.target.value || null })
                  }
                  placeholder="Their contact number"
                />
              </EditField>
              <EditField id="quotation-attn-name" label="Attn">
                <Input
                  id="quotation-attn-name"
                  value={document.attn_name ?? ''}
                  onChange={(event) => onChange({ attn_name: event.target.value || null })}
                  placeholder="The person who will read it"
                />
              </EditField>
            </div>
          ) : (
            <>
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
            </>
          )}
        </div>

        <div className="min-w-0 space-y-2 md:justify-self-end md:text-left">
          {/* Our Ref stays a read even in a session: it is the number the customer already has,
              minted by the numbering rule, and the backend refuses to edit it for that reason. */}
          <Field label="Our Ref" value={document.our_ref ?? document.document_no} />
          {onChange ? (
            <div className="space-y-3">
              <EditField id="quotation-your-ref" label="Your Ref">
                <Input
                  id="quotation-your-ref"
                  value={document.your_ref ?? ''}
                  onChange={(event) => onChange({ your_ref: event.target.value || null })}
                  placeholder="Their reference, as they quote it"
                />
              </EditField>
              {/* The module's own date control - every other date in project sales (the PO
                  header, the sample, the task) is this same one, and it holds the ISO string
                  the API already speaks, so nothing has to be parsed back out of a Date. */}
              <EditField id="quotation-doc-date" label="Date">
                <Input
                  id="quotation-doc-date"
                  type="date"
                  value={(document.doc_date ?? '').slice(0, 10)}
                  onChange={(event) => onChange({ doc_date: event.target.value || null })}
                />
              </EditField>
            </div>
          ) : (
            <>
              <Field label="Your Ref" value={document.your_ref ?? '-'} />
              <Field label="Date" value={docDate || '-'} />
            </>
          )}
          {/* The total belongs with the refs, not beside the buttons in the page header. It is a
              FACT about the document, the same kind as its date, and the client asked for it here.
              Up in the header it competed with the primary action for the eye.

              The live figure wins whenever there is one: what the reader is owed is the total of
              what is ON THE SCREEN, not the total of what was last saved. */}
          <div className="flex gap-2 border-t border-border pt-2 text-sm">
            <span className="w-20 shrink-0 text-muted-foreground">Total</span>
            <span className="font-semibold tabular-nums">
              {formatMyrExact(liveGrandTotal ?? document.grand_total)}
            </span>
          </div>
        </div>

        <div className="border-t border-border pt-4 md:col-span-2">
          {onChange ? (
            <EditField id="quotation-subject-title" label="Subject">
              <Input
                id="quotation-subject-title"
                value={document.subject_title ?? ''}
                onChange={(event) => onChange({ subject_title: event.target.value || null })}
                placeholder="The one line naming the job"
              />
            </EditField>
          ) : (
            <p className="min-w-0 break-words text-sm font-semibold uppercase tracking-wide">
              {document.subject_title ?? '-'}
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
