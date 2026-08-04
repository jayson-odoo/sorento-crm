'use client';

import * as React from 'react';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { SignaturePad } from '@/components/common/SignaturePad';
import { signatureValueFrom } from '@/components/common/signatureValue';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import type {
  QuotationDocument,
  QuotationSignatureRecord,
} from '../../../../_shared/services/quotationDocumentService';

/**
 * Both signatures on the quotation, laid out like the handover screen the client pointed at.
 *
 * Every half renders in every state, empty ones included. An issued quotation the customer never
 * counter-signs is a complete CRM record (AC-H8), and a section that disappeared would read as
 * "we did not record it" when the honest answer is "nothing has been captured yet".
 *
 * Rendered through the shared `SignaturePad readOnly`, not a bespoke image box, so the ink and its
 * metadata look identical here and on the customer's counter-sign page.
 */
function EmptyBox({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-md border border-dashed border-border p-4">
      <p className="min-w-0 break-words text-sm text-muted-foreground">{children}</p>
    </div>
  );
}

export function QuotationSignatureBlock({
  document,
  sorentoSignature = null,
  customerSignature = null,
  acceptedAt = null,
}: {
  document: QuotationDocument;
  /** Passed in rather than read off `document`: the screen owns where it got the signature. */
  sorentoSignature?: QuotationSignatureRecord | null;
  /**
   * The counter-signature, which lives on the ISSUE. Not carried by the document contract, so it
   * is a prop rather than a read off `document`: the counter-sign page has it today, and this
   * panel starts showing it the moment an internal route serializes it.
   */
  customerSignature?: QuotationSignatureRecord | null;
  acceptedAt?: string | null;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <CardTitle className="min-w-0 break-words text-sm">Signatures</CardTitle>
        {acceptedAt ? (
          <Badge variant="success" appearance="light">
            {`Accepted ${formatDateTimeInMalaysia(acceptedAt)}`}
          </Badge>
        ) : (
          <Badge variant="secondary" appearance="light">
            {document.is_issued ? 'Awaiting counter-signature' : 'Not issued yet'}
          </Badge>
        )}
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
          {sorentoSignature ? (
            <SignaturePad
              readOnly
              onChange={() => {}}
              value={signatureValueFrom(sorentoSignature)}
              label={sorentoSignature.signer_name?.trim() || document.signatory_name || 'Signature'}
              extraMetadata={[{ label: 'IP address', value: sorentoSignature.ip_address }]}
            />
          ) : document.is_issued ? (
            // An issued document was signed - the server refuses to issue an unsigned one - so
            // saying "not signed" here would be a lie. What is true is that this screen has not
            // been handed the image on this page load.
            <EmptyBox>
              This quotation was signed before it was issued. The signature is on the issued PDF.
            </EmptyBox>
          ) : (
            <EmptyBox>
              No signature captured on this quotation yet. Use Sign, above, before issuing it.
            </EmptyBox>
          )}
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
          {customerSignature ? (
            <SignaturePad
              readOnly
              onChange={() => {}}
              value={signatureValueFrom(customerSignature)}
              label={
                customerSignature.signer_name?.trim() || document.attn_name || 'Customer signature'
              }
              extraMetadata={[{ label: 'IP address', value: customerSignature.ip_address }]}
            />
          ) : document.is_issued ? (
            <EmptyBox>
              The customer has not counter-signed yet. That is a normal resting state for an issued
              quotation, not an error.
            </EmptyBox>
          ) : (
            <EmptyBox>
              Issue this quotation to send the customer a link they can counter-sign.
            </EmptyBox>
          )}
        </section>
      </CardContent>
    </Card>
  );
}
