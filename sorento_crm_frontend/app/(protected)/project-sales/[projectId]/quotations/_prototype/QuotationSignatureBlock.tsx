'use client';

import * as React from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import type { MockDocument } from './documentMocks';

/**
 * Both signatures on the quotation, laid out like the handover screen the client pointed
 * at: the ink on a white canvas, and the facts that make it evidence beside it.
 *
 * Two decisions this screen makes visible:
 *
 * - **GPS renders as `-`, never hidden.** The browser gives coordinates or it does not, and
 *   a field that quietly disappears reads as "we did not record it" when the honest answer
 *   is "it was not available" (AC-H4).
 * - **An unsigned customer block is a resting state, not a fault.** An issued quotation the
 *   customer never counter-signs is a complete CRM record, so it is coloured and worded as
 *   waiting rather than as an error (AC-H8).
 *
 * The pad itself - draw / type / initials - is slice S5. `onSign` is a stub here.
 */
function MetaField({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="min-w-0">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <p className="min-w-0 break-words text-sm">{value ?? '-'}</p>
    </div>
  );
}

/**
 * Placeholder ink. Phase 2 renders the stored PNG here; the canvas stays white in both
 * themes because a signature is ink on paper, not a themed surface.
 */
function SignatureInk({ label }: { label: string }) {
  return (
    <div className="flex h-24 w-full max-w-56 items-center justify-center rounded-md border border-border bg-white">
      <svg
        viewBox="0 0 200 70"
        className="h-16 w-44 text-slate-900"
        role="img"
        aria-label={label}
      >
        <path
          d="M8 48 C 24 14, 38 12, 44 30 C 50 48, 42 58, 36 52 C 30 46, 44 30, 62 34 C 74 37, 78 46, 88 44 C 100 42, 104 20, 116 24 C 126 28, 118 50, 128 52 C 140 54, 150 30, 162 28 C 172 27, 176 40, 192 34"
          fill="none"
          stroke="currentColor"
          strokeWidth={3}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </div>
  );
}

export function QuotationSignatureBlock({
  document,
  canEdit,
  onSign,
}: {
  document: MockDocument;
  canEdit: boolean;
  onSign?: () => void;
}) {
  const signed = Boolean(document.signed_at);
  const countersigned = Boolean(document.customer_signed_at);

  return (
    <Card>
      <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <CardTitle className="min-w-0 break-words text-sm">Signatures</CardTitle>
        {countersigned ? (
          <Badge variant="success" appearance="light">
            Accepted
          </Badge>
        ) : (
          <Badge variant="secondary" appearance="light">
            Awaiting counter-signature
          </Badge>
        )}
      </CardHeader>

      <CardContent className="space-y-6 py-5">
        <section className="space-y-3">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            Sorento
          </p>
          <div>
            <p className="min-w-0 break-words text-sm font-medium">{document.signatory.name}</p>
            <p className="min-w-0 break-words text-sm text-muted-foreground">
              {document.signatory.phone}
            </p>
          </div>

          {signed ? (
            <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:gap-6">
              <SignatureInk label={`Signature of ${document.signatory.name}`} />
              <div className="grid min-w-0 flex-1 gap-3 sm:grid-cols-3">
                <MetaField
                  label="Signed at"
                  value={
                    document.signed_at ? formatDateTimeInMalaysia(document.signed_at) : null
                  }
                />
                <MetaField label="IP address" value={document.signature_ip} />
                <MetaField label="GPS location" value={document.signature_gps} />
              </div>
            </div>
          ) : (
            <div className="flex flex-col gap-3 rounded-md border border-dashed border-border p-4 sm:flex-row sm:items-center sm:justify-between">
              <p className="min-w-0 break-words text-sm text-muted-foreground">
                Not signed yet. A quotation cannot be issued unsigned.
              </p>
              {canEdit && (
                // Stub: opens the signature pad in S5.
                <Button size="sm" onClick={onSign}>
                  Sign
                </Button>
              )}
            </div>
          )}
        </section>

        <section className="space-y-3 border-t border-border pt-6">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            Customer
          </p>
          <div>
            <p className="min-w-0 break-words text-sm font-medium">{document.recipient.name}</p>
            <p className="min-w-0 break-words text-sm text-muted-foreground">
              {document.attn_name ?? '-'}
            </p>
          </div>

          {countersigned ? (
            <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:gap-6">
              <SignatureInk label={`Signature of ${document.recipient.name}`} />
              <div className="grid min-w-0 flex-1 gap-3 sm:grid-cols-3">
                <MetaField
                  label="Accepted at"
                  value={
                    document.customer_signed_at
                      ? formatDateTimeInMalaysia(document.customer_signed_at)
                      : null
                  }
                />
                <MetaField label="IP address" value={null} />
                <MetaField label="GPS location" value={null} />
              </div>
            </div>
          ) : (
            <div className="rounded-md border border-dashed border-border p-4">
              <p className="min-w-0 break-words text-sm text-muted-foreground">
                The customer has not counter-signed yet. That is a normal resting state for an
                issued quotation, not an error.
              </p>
            </div>
          )}
        </section>
      </CardContent>
    </Card>
  );
}
