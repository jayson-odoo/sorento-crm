'use client';

import * as React from 'react';
import { CheckCircle2, Link2Off } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { SignaturePad } from '@/components/common/SignaturePad';
import { signatureValueFrom } from '@/components/common/signatureValue';
import { formatDateInMalaysia, formatDateTimeInMalaysia } from '@/lib/helpers';
import { sanitizedHtml } from '@/lib/sanitize';
import { useQuotationSignMutations, useQuotationSignPage } from '../../hooks/useQuotationSign';
import { QuotationSignError, type QuotationSignPage } from '../../services/quotationSignService';
import { QuotationSignScopes } from './QuotationSignScopes';

function text(value: string | null | undefined): string {
  return value?.trim() ? value : '-';
}

function addressLines(address: string | null): string[] {
  if (!address) return [];
  return address
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
}

/** The refs and the parties, in the order they sit on the printed quotation. */
function Letterhead({ page }: { page: QuotationSignPage }) {
  const lines = addressLines(page.recipient_address);
  const docDate = page.doc_date ? formatDateInMalaysia(page.doc_date) : '';

  return (
    <Card>
      <CardContent className="space-y-5 py-5">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Quotation from
          </p>
          <p className="min-w-0 break-words text-base font-semibold">{text(page.sender_name)}</p>
        </div>

        <div className="grid gap-5 border-t border-border pt-4 md:grid-cols-2">
          <div className="min-w-0 space-y-1">
            <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              To
            </p>
            <p className="min-w-0 break-words text-sm font-medium">{text(page.recipient_name)}</p>
            {lines.length > 0 ? (
              lines.map((row) => (
                <p key={row} className="min-w-0 break-words text-sm text-muted-foreground">
                  {row}
                </p>
              ))
            ) : (
              <p className="text-sm text-muted-foreground">-</p>
            )}
            <p className="mt-2 text-sm">
              <span className="text-muted-foreground">Attn: </span>
              <span className="font-medium">{text(page.attn_name)}</span>
            </p>
          </div>

          <div className="min-w-0 space-y-2 md:justify-self-end">
            <div className="flex gap-2 text-sm">
              <span className="w-20 shrink-0 text-muted-foreground">Our Ref</span>
              <span className="min-w-0 break-words font-medium">{text(page.our_ref)}</span>
            </div>
            <div className="flex gap-2 text-sm">
              <span className="w-20 shrink-0 text-muted-foreground">Revision</span>
              <span className="font-medium">{`R${page.issue_no}`}</span>
            </div>
            <div className="flex gap-2 text-sm">
              <span className="w-20 shrink-0 text-muted-foreground">Date</span>
              <span className="font-medium">{docDate || '-'}</span>
            </div>
          </div>
        </div>

        <div className="min-w-0 border-t border-border pt-4">
          <p className="min-w-0 break-words text-sm font-semibold uppercase tracking-wide">
            {text(page.subject_title)}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

/**
 * The letter and the terms as the issue froze them.
 *
 * Through `sanitizedHtml` because the stored copy is editable prose - untrusted input no matter
 * who last typed in it - and this page renders it for somebody outside the company.
 */
function ProsePanel({ title, html, empty }: { title: string; html: string | null; empty: string }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="min-w-0 break-words text-sm">{title}</CardTitle>
      </CardHeader>
      <CardContent className="py-5">
        {html?.trim() ? (
          <div
            className="prose prose-sm max-w-none break-words text-sm"
            dangerouslySetInnerHTML={sanitizedHtml(html)}
          />
        ) : (
          <p className="min-w-0 break-words text-sm text-muted-foreground">{empty}</p>
        )}
      </CardContent>
    </Card>
  );
}

/**
 * The customer's half: sign it, or read back what was signed.
 *
 * The name is asked for BEFORE the pad unlocks, because a signature with no name beside it is
 * weaker evidence than one with it, and prefilled from `Attn:` so the usual signer confirms
 * rather than types. Once accepted there is no signing affordance at all - not a disabled one:
 * offering to sign something already signed invites a second attempt that the backend would
 * ignore anyway.
 */
function CustomerSignature({ page, token }: { page: QuotationSignPage; token: string }) {
  const { accept } = useQuotationSignMutations(token);
  const [signerName, setSignerName] = React.useState(page.attn_name ?? '');
  const named = signerName.trim().length > 0;

  if (page.is_accepted) {
    return (
      <Card>
        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <CardTitle className="min-w-0 break-words text-sm">Your signature</CardTitle>
          <Badge variant="success" appearance="light">
            <CheckCircle2 className="size-3.5" aria-hidden />
            Accepted
          </Badge>
        </CardHeader>
        <CardContent className="space-y-4 py-5">
          <p className="min-w-0 break-words text-sm text-muted-foreground">
            {page.accepted_at
              ? `Accepted on ${formatDateTimeInMalaysia(page.accepted_at)}.`
              : 'This quotation has been accepted.'}
          </p>
          <SignaturePad
            readOnly
            onChange={() => {}}
            value={signatureValueFrom(page.customer_signature)}
            // The signer's own name heads their signature. Falls back to a label rather than to
            // `-`: a card titled "-" reads as a fault, and this one is not a data field.
            label={
              page.customer_signature?.signer_name?.trim() ||
              page.attn_name?.trim() ||
              'Your signature'
            }
            extraMetadata={[
              { label: 'IP address', value: page.customer_signature?.ip_address ?? null },
            ]}
          />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="min-w-0 break-words text-sm">Accept this quotation</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 py-5">
        <p className="min-w-0 break-words text-sm text-muted-foreground">
          Signing below accepts this quotation.
        </p>

        <div className="space-y-1.5">
          <Label htmlFor="quotation-sign-name">Your name</Label>
          <Input
            id="quotation-sign-name"
            value={signerName}
            autoComplete="name"
            placeholder="As it should read on the quotation"
            disabled={accept.isPending}
            onChange={(event) => setSignerName(event.target.value)}
          />
          {!named && (
            <p className="text-xs text-muted-foreground">Enter your name to sign.</p>
          )}
        </div>

        <SignaturePad
          label="Sign here"
          commitLabel="Sign and accept"
          typedNameDefault={signerName}
          // Locked until there is a name to put beside the ink. The pad owns its own Apply
          // button, so gating it here is the only way to keep the two in the right order.
          disabled={!named || accept.isPending}
          onChange={(value) => {
            if (!value) return;
            accept.mutate({
              signer_name: signerName.trim(),
              mode: value.mode,
              image_data_uri: value.dataUrl,
              // Stringified rather than sent as JSON numbers: the column is NUMERIC(10,7) and a
              // float round-trip is a needless chance to move the coordinate.
              gps_lat: value.gpsLat === null ? null : String(value.gpsLat),
              gps_lng: value.gpsLng === null ? null : String(value.gpsLng),
            });
          }}
        />

        {accept.isPending && (
          <p className="text-sm text-muted-foreground">Saving your signature...</p>
        )}
      </CardContent>
    </Card>
  );
}

/**
 * The page's own width, because the (auth) shell hands this route the raw viewport.
 *
 * A quotation is a WIDE document: nine columns of line items that the reader has to compare
 * before signing. Framed in the branded card's fixed column it sat between two empty margins on a
 * desktop screen while the table scrolled inside it, so the width goes to the table instead.
 * Capped all the same - a line of text run across an ultrawide monitor is its own kind of
 * unreadable - and `min-w-0` so the table scrolls in its own gutter rather than dragging the page
 * sideways at 375px.
 */
function PageShell({ children, testId }: { children: React.ReactNode; testId: string }) {
  return (
    <div
      data-testid={testId}
      // `overflow-x-clip` rather than `-hidden`: clip stops a stray wide child dragging the page
      // sideways WITHOUT turning this div into a scroll container (hidden forces overflow-y to
      // auto, which would nest a second vertical scrollbar inside the shell's own).
      className="mx-auto min-w-0 w-full max-w-[1600px] space-y-4 overflow-x-clip px-4 py-6 sm:px-6"
    >
      {children}
    </div>
  );
}

/**
 * The whole counter-sign page, driven by one public GET.
 *
 * No app chrome: the reader is a stranger on a phone who arrived from a WhatsApp link, and the
 * only two things they can do here are read the quotation and sign it.
 */
export function QuotationSignClient({ token }: { token: string }) {
  const query = useQuotationSignPage(token);

  if (query.isLoading) {
    return (
      <PageShell testId="quotation-sign-loading">
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-64 w-full" />
      </PageShell>
    );
  }

  if (query.isError || !query.data) {
    const dead = query.error instanceof QuotationSignError && query.error.isDeadLink;
    // A dead link is the expected end of an expired invitation, so it reads as a plain fact with
    // the one action that helps. Anything else is a fault the reader can retry out of.
    return (
      <PageShell testId="quotation-sign-unavailable">
        <Card>
          <CardContent className="px-4 py-10 text-center sm:px-6">
            <Link2Off className="mx-auto size-6 text-muted-foreground" aria-hidden />
            <h1 className="mt-3 text-base font-semibold">
              {dead ? 'This link is no longer valid' : 'This quotation could not be loaded'}
            </h1>
            <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
              {dead
                ? 'Ask your contact at Sorento to resend it.'
                : query.error instanceof Error
                  ? query.error.message
                  : 'Please try again in a moment.'}
            </p>
            {!dead && (
              <Button
                type="button"
                variant="outline"
                className="mt-4"
                onClick={() => void query.refetch()}
              >
                Try again
              </Button>
            )}
          </CardContent>
        </Card>
      </PageShell>
    );
  }

  const page = query.data;

  return (
    <PageShell testId="quotation-sign-page">
      <Letterhead page={page} />

      <ProsePanel
        title="Cover letter"
        html={page.cover_letter}
        empty="No cover letter was included with this quotation."
      />

      <QuotationSignScopes scopes={page.scopes} grandTotal={page.grand_total} />

      <ProsePanel
        title="Terms and conditions"
        html={page.terms}
        empty="No terms were included with this quotation."
      />

      <Card>
        <CardHeader>
          <CardTitle className="min-w-0 break-words text-sm">Signed for Sorento</CardTitle>
        </CardHeader>
        <CardContent className="py-5">
          <SignaturePad
            readOnly
            onChange={() => {}}
            value={signatureValueFrom(page.sorento_signature)}
            label={text(page.sorento_signature?.signer_name ?? page.signatory_name)}
          />
        </CardContent>
      </Card>

      <CustomerSignature page={page} token={token} />
    </PageShell>
  );
}
