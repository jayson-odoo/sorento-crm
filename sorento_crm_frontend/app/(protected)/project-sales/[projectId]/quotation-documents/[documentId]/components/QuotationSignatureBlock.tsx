'use client';

import * as React from 'react';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { QuotationDocument } from '../../../../_shared/services/quotationDocumentService';

/**
 * Both signatures on the quotation, laid out like the handover screen the client pointed at.
 *
 * The document contract carries the SIGNATORY (who signs for Sorento) but no captured ink,
 * timestamp, IP or GPS yet - the signature pad is slice S5. So both halves render as resting
 * states rather than being hidden: an issued quotation the customer never counter-signs is a
 * complete CRM record, and a section that disappears reads as "we did not record it" when the
 * honest answer is "nothing has been captured yet".
 */
export function QuotationSignatureBlock({ document }: { document: QuotationDocument }) {
  return (
    <Card>
      <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <CardTitle className="min-w-0 break-words text-sm">Signatures</CardTitle>
        <Badge variant="secondary" appearance="light">
          Awaiting counter-signature
        </Badge>
      </CardHeader>

      <CardContent className="space-y-6 py-5">
        <section className="space-y-3">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            Sorento
          </p>
          <div>
            <p className="min-w-0 break-words text-sm font-medium">
              {document.signatory_name ?? '-'}
            </p>
            <p className="min-w-0 break-words text-sm text-muted-foreground">
              {document.signatory_phone ?? '-'}
            </p>
          </div>
          <div className="rounded-md border border-dashed border-border p-4">
            <p className="min-w-0 break-words text-sm text-muted-foreground">
              No signature captured on this quotation yet.
            </p>
          </div>
        </section>

        <section className="space-y-3 border-t border-border pt-6">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            Customer
          </p>
          <div>
            <p className="min-w-0 break-words text-sm font-medium">
              {document.recipient_name_snapshot ?? '-'}
            </p>
            <p className="min-w-0 break-words text-sm text-muted-foreground">
              {document.attn_name ?? '-'}
            </p>
          </div>
          <div className="rounded-md border border-dashed border-border p-4">
            <p className="min-w-0 break-words text-sm text-muted-foreground">
              The customer has not counter-signed yet. That is a normal resting state for an
              issued quotation, not an error.
            </p>
          </div>
        </section>
      </CardContent>
    </Card>
  );
}
