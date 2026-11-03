'use client';

import * as React from 'react';
import {
  AlertCircle,
  CheckCircle2,
  Info,
  Link2Off,
  MessageSquareText,
  Replace,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { SignaturePad } from '@/components/common/SignaturePad';
import { signatureValueFrom } from '@/components/common/signatureValue';
import { cn } from '@/lib/utils';
import { formatDateInMalaysia, formatDateTimeInMalaysia } from '@/lib/helpers';
import { sanitizedHtml } from '@/lib/sanitize';
import { CoverPageCard, SenderRow } from '@/components/quotation/CoverPageCard';
import {
  useQuotationSignMutations,
  useQuotationSignPage,
} from '../../hooks/useQuotationSign';
import { useQuotationViewBeacon } from '../../hooks/useQuotationViewBeacon';
import {
  QuotationSignError,
  type QuotationSignPage,
} from '../../services/quotationSignService';
import { QuotationSignScopes } from './QuotationSignScopes';
import { FeedbackDialog, NoteDialog } from './QuotationSignFeedback';
import {
  feedbackBody,
  feedbackItem,
  type FeedbackTarget,
} from './quotationSuggest';

/** "Proposal" or "Quotation": what the customer is holding (PS-PROPOSAL-QUOTATION). */
function noun(page: QuotationSignPage): string {
  return page.document_kind === 'quotation' ? 'Quotation' : 'Proposal';
}

/** "Quotation No. X", whether or not the ref already carries the label. */
function quotationLabel(ref: string, word = 'Quotation'): string {
  return /^(quotation|proposal) no\./i.test(ref.trim())
    ? ref.trim()
    : `${word} No. ${ref.trim()}`;
}

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

/** The first non-blank name, trimmed; null when every candidate is blank. */
function firstName(...names: Array<string | null | undefined>): string | null {
  for (const name of names) {
    if (name?.trim()) return name.trim();
  }
  return null;
}

/** The refs and the parties, in the order they sit on the printed quotation. */
function Letterhead({
  page,
  withSender = true,
}: {
  page: QuotationSignPage;
  withSender?: boolean;
}) {
  const lines = addressLines(page.recipient_address);
  const docDate = page.doc_date ? formatDateInMalaysia(page.doc_date) : '';
  const salesContact = [page.signatory_name, page.signatory_phone]
    .map((part) => part?.trim())
    .filter(Boolean)
    .join(', ');

  return (
    <Card>
      <CardContent className="space-y-5 py-5">
        {withSender && (
          <SenderRow name={page.sender_name} logoUrl={page.sender_logo_url} noun={noun(page)} />
        )}

        <div
          className={cn(
            'grid gap-5 md:grid-cols-2',
            withSender && 'border-t border-border pt-4',
          )}
        >
          <div className="min-w-0 space-y-1">
            <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              To
            </p>
            <p className="min-w-0 break-words text-sm font-medium">
              {text(page.recipient_name)}
            </p>
            {lines.length > 0 ? (
              lines.map((row) => (
                <p
                  key={row}
                  className="min-w-0 break-words text-sm text-muted-foreground"
                >
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
              <span className="w-28 shrink-0 text-muted-foreground">
                {`${noun(page)} No.`}
              </span>
              <span className="min-w-0 break-words font-medium">
                {text(page.our_ref)}
              </span>
            </div>
            <div className="flex gap-2 text-sm">
              <span className="w-28 shrink-0 text-muted-foreground">
                Revision
              </span>
              <span className="font-medium">{`R${page.issue_no}`}</span>
            </div>
            <div className="flex gap-2 text-sm">
              <span className="w-28 shrink-0 text-muted-foreground">Date</span>
              <span className="font-medium">{docDate || '-'}</span>
            </div>
            {salesContact && (
              <div className="flex gap-2 text-sm">
                <span className="w-28 shrink-0 text-muted-foreground">
                  Sales contact
                </span>
                <span className="min-w-0 break-words font-medium">
                  {salesContact}
                </span>
              </div>
            )}
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
function ProsePanel({
  title,
  html,
  empty,
}: {
  title: string;
  html: string | null;
  empty: string;
}) {
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
          <p className="min-w-0 break-words text-sm text-muted-foreground">
            {empty}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

/**
 * The customer's half: sign it, ask for a revision, or read back the decision already taken.
 *
 * The name is asked for BEFORE the pad unlocks, because a signature with no name beside it is
 * weaker evidence than one with it, and prefilled from `Attn:` so the usual signer confirms
 * rather than types. The same name rides along with a change request, which carries no signature
 * and would otherwise reach the salesperson from "somebody".
 *
 * Once a decision is taken there is no affordance for it at all - not a disabled one: offering to
 * sign something already signed invites a second attempt the backend would ignore anyway.
 * Acceptance is checked FIRST because both fields can be set: a customer who asked for changes
 * and then signed has accepted, and that is what the page must say.
 */
function CustomerSignature({
  page,
  token,
  signerName,
  onSignerName,
}: {
  page: QuotationSignPage;
  token: string;
  signerName: string;
  onSignerName: (name: string) => void;
}) {
  const { accept } = useQuotationSignMutations(token);
  const named = signerName.trim().length > 0;
  const hasTerms = Boolean(page.terms?.trim());
  const [ticked, setTicked] = React.useState(false);
  // Set once the customer taps Sign and accept (or the locked pad) before it is ready: the hint
  // then turns to the warning colour until everything is in.
  const [nudged, setNudged] = React.useState(false);
  const nameRef = React.useRef<HTMLInputElement | null>(null);
  const tickRef = React.useRef<HTMLButtonElement | null>(null);
  const padRef = React.useRef<HTMLDivElement | null>(null);
  const termsOk = !hasTerms || ticked;

  if (page.is_accepted) {
    return (
      <Card>
        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <CardTitle className="min-w-0 break-words text-sm">
            {['Accepted by', page.customer_signature?.signer_name?.trim()]
              .filter(Boolean)
              .join(' ')}
          </CardTitle>
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
            hideLocation
            requestGeolocation={false}
            // The signer's own name heads their signature. Falls back to a label rather than to
            // `-`: a card titled "-" reads as a fault, and this one is not a data field.
            label={
              page.customer_signature?.signer_name?.trim() ||
              page.attn_name?.trim() ||
              'Your signature'
            }
            extraMetadata={[
              {
                label: 'IP address',
                value: page.customer_signature?.ip_address ?? null,
              },
            ]}
          />
        </CardContent>
      </Card>
    );
  }

  // A newer revision replaced this one: nothing here can be signed or given feedback any more.
  if (page.sign_blocked_reason === 'superseded' && page.superseded_by_ref) {
    return (
      <Card>
        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <CardTitle className="min-w-0 break-words text-sm">
            Replaced
          </CardTitle>
          <Badge variant="secondary" appearance="light">
            <Replace className="size-3.5" aria-hidden />
            Replaced
          </Badge>
        </CardHeader>
        <CardContent className="py-5">
          <p className="min-w-0 break-words text-sm">
            {`This ${noun(page).toLowerCase()} has been replaced by ${quotationLabel(page.superseded_by_ref, noun(page))}.`}
          </p>
        </CardContent>
      </Card>
    );
  }

  /**
   * The older free-text request, for an issue that carries one and no suggested changes. A form
   * still sitting here is how somebody sends the same message four times, so the request replaces
   * it - and the words are quoted back as proof that it arrived.
   */
  if (page.is_changes_requested && !page.amendment_request) {
    return (
      <Card>
        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <CardTitle className="min-w-0 break-words text-sm">
            Your response
          </CardTitle>
          <Badge variant="warning" appearance="light">
            <MessageSquareText className="size-3.5" aria-hidden />
            Changes requested
          </Badge>
        </CardHeader>
        <CardContent className="space-y-4 py-5">
          <p className="min-w-0 break-words text-sm text-muted-foreground">
            {page.changes_requested_at
              ? `Sent on ${formatDateTimeInMalaysia(page.changes_requested_at)}.`
              : 'Your request has been sent.'}
          </p>
          <blockquote className="min-w-0 whitespace-pre-line break-words rounded-md border border-border bg-muted/40 p-4 text-sm">
            {text(page.changes_requested_note)}
          </blockquote>
          <p className="min-w-0 break-words text-sm text-muted-foreground">
            {page.signatory_name
              ? `${page.signatory_name} will follow up with a revised quotation.`
              : 'Sorento will follow up with a revised quotation.'}
          </p>
        </CardContent>
      </Card>
    );
  }

  /** The first step still missing, named for the hint and the element to bring into view. */
  function hintFor(hasContent: boolean): string | null {
    if (!named) {
      return hasTerms
        ? 'Type your name and tick the terms box to accept.'
        : 'Type your name to accept.';
    }
    if (!termsOk) return 'Tick to agree to the terms before you accept.';
    return hasContent ? null : 'Draw your signature to accept.';
  }

  function showMissingStep() {
    setNudged(true);
    const target = !named
      ? nameRef.current
      : !termsOk
        ? tickRef.current
        : padRef.current;
    target?.scrollIntoView?.({ block: 'center' });
    if (!named || !termsOk) target?.focus();
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="min-w-0 break-words text-sm">
          Accepted by
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 py-5">
        <p className="min-w-0 break-words text-sm text-muted-foreground">
          Signing below accepts this quotation.
        </p>

        <div className="space-y-1.5">
          <Label htmlFor="quotation-sign-name">Your name</Label>
          <Input
            id="quotation-sign-name"
            ref={nameRef}
            value={signerName}
            autoComplete="name"
            placeholder="As it should read on the quotation"
            disabled={accept.isPending}
            onChange={(event) => onSignerName(event.target.value)}
          />
        </div>

        {hasTerms && (
          <div
            data-attention={nudged && named && !ticked ? 'true' : undefined}
            className="flex items-start gap-2 rounded-md border border-transparent p-2 data-[attention=true]:border-warning data-[attention=true]:bg-warning/10"
          >
            <Checkbox
              id="quotation-sign-terms"
              ref={tickRef}
              checked={ticked}
              disabled={accept.isPending}
              onCheckedChange={(next) => setTicked(next === true)}
            />
            <Label
              htmlFor="quotation-sign-terms"
              className="min-w-0 break-words leading-snug"
            >
              I have read and agree to the Terms and conditions.
            </Label>
          </div>
        )}

        <div ref={padRef}>
          <SignaturePad
            label="Sign here"
            hideLocation
            requestGeolocation={false}
            commitLabel="Sign and accept"
            typedNameDefault={signerName}
            // Locked until there is a name to put beside the ink. The pad owns its own Apply
            // button, so gating it here is the only way to keep the two in the right order.
            disabled={!named || !termsOk || accept.isPending}
            onNotReadyAttempt={showMissingStep}
            renderFooterHint={({ hasContent, hintId }) => {
              const hint = hintFor(hasContent);
              if (!hint) return null;
              const HintIcon = nudged ? AlertCircle : Info;
              return (
                <p
                  id={hintId}
                  aria-live="polite"
                  className={cn(
                    'order-last flex min-w-0 basis-full items-start gap-1.5 text-sm sm:order-none sm:basis-0 sm:flex-1',
                    nudged
                      ? 'font-medium text-warning'
                      : 'text-muted-foreground',
                  )}
                >
                  <HintIcon className="mt-0.5 size-4 shrink-0" aria-hidden />
                  {hint}
                </p>
              );
            }}
            onChange={(value) => {
              if (!value) return;
              accept.mutate({
                signer_name: signerName.trim(),
                mode: value.mode,
                image_data_uri: value.dataUrl,
                // Stringified rather than sent as JSON numbers: the column is NUMERIC(10,7) and a
                // float round-trip is a needless chance to move the coordinate.
                // The sign page never asks for location.
                gps_lat: null,
                gps_lng: null,
                terms_accepted: ticked,
              });
            }}
          />
        </div>

        {accept.isPending && (
          <p className="text-sm text-muted-foreground">
            Saving your signature...
          </p>
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
function PageShell({
  children,
  testId,
}: {
  children: React.ReactNode;
  testId: string;
}) {
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
  // Counted only once the quotation is on screen: a dead link is not a view.
  useQuotationViewBeacon(token, Boolean(query.data));

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
    const dead =
      query.error instanceof QuotationSignError && query.error.isDeadLink;
    // A dead link is the expected end of an expired invitation, so it reads as a plain fact with
    // the one action that helps. Anything else is a fault the reader can retry out of.
    return (
      <PageShell testId="quotation-sign-unavailable">
        <Card>
          <CardContent className="px-4 py-10 text-center sm:px-6">
            <Link2Off
              className="mx-auto size-6 text-muted-foreground"
              aria-hidden
            />
            <h1 className="mt-3 text-base font-semibold">
              {dead
                ? 'This link is no longer valid'
                : 'This quotation could not be loaded'}
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

  return <SignPageBody page={query.data} token={token} />;
}

/**
 * The loaded page. Its own component so the name and the feedback state can start from the
 * page itself: the name the customer types travels with a signature and with feedback alike.
 */
function SignPageBody({
  page,
  token,
}: {
  page: QuotationSignPage;
  token: string;
}) {
  const { submitFeedback } = useQuotationSignMutations(token);
  const [signerName, setSignerName] = React.useState(page.attn_name ?? '');
  // The item or cell the feedback form is open on, and the free-note form (PS-QUOTE-MATRIX R19).
  const [target, setTarget] = React.useState<FeedbackTarget | null>(null);
  const [noting, setNoting] = React.useState(false);
  const sending = submitFeedback.isPending;
  // Feedback never blocks signing and may be sent more than once; it ends once the quotation is
  // signed or replaced by a newer revision, and an older free-text request settled here keeps
  // its own resting state.
  const canFeedback =
    !page.is_accepted &&
    page.sign_blocked_reason !== 'superseded' &&
    !(page.is_changes_requested && !page.amendment_request);

  const coverRows = page.cover_rows?.length ? page.cover_rows : null;
  // Layout 3 (a designed cover) names its title; layouts 1 and 2 do not.
  const designed = page.cover_title != null;
  // The terms print inside the cover while their row is shown; below the prices otherwise.
  const termsOnCover = coverRows?.some((row) => row.key === 'terms') ?? false;
  const preparedBy = firstName(
    page.sorento_signature?.signer_name,
    page.signatory_name,
    page.sender_name,
  );

  return (
    <PageShell testId="quotation-sign-page">
      {(coverRows || designed) && (
        <CoverPageCard
          cover={{ ...page, cover_rows: coverRows ?? [] }}
          testId="quotation-sign-cover"
          noun={noun(page)}
        />
      )}
      <Letterhead page={page} withSender={!coverRows && !designed} />

      {/* A designed cover carries the letter as its intro. */}
      {!designed && (
        <ProsePanel
          title="Cover letter"
          html={page.cover_letter}
          empty="No cover letter was included with this quotation."
        />
      )}

      <QuotationSignScopes
        scopes={page.scopes}
        grandTotal={page.grand_total}
        sent={page.amendment_request ?? null}
        onFeedback={canFeedback ? setTarget : undefined}
        action={
          canFeedback ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setNoting(true)}
            >
              Leave a note
            </Button>
          ) : null
        }
      />

      <FeedbackDialog
        target={target}
        sending={sending}
        onClose={() => setTarget(null)}
        onSend={(draft) => {
          if (!target) return;
          submitFeedback.mutate(
            feedbackBody([feedbackItem(target, draft)], '', signerName),
            { onSuccess: () => setTarget(null) },
          );
        }}
      />

      <NoteDialog
        open={noting}
        sending={sending}
        onClose={() => setNoting(false)}
        onSend={(note) =>
          submitFeedback.mutate(feedbackBody([], note, signerName), {
            onSuccess: () => setNoting(false),
          })
        }
      />

      {((!coverRows && !designed) || (designed && !termsOnCover)) && (
        <ProsePanel
          title="Terms and conditions"
          html={page.terms}
          empty="No terms were included with this quotation."
        />
      )}

      {/* Side by side from 768px, Sorento first; stacked below it so a phone reads top down. */}
      <div className="grid items-start gap-4 md:grid-cols-2">
        <Card className="min-w-0">
          <CardHeader>
            <CardTitle className="min-w-0 break-words text-sm">
              {['Prepared by', preparedBy].filter(Boolean).join(' ')}
            </CardTitle>
          </CardHeader>
          <CardContent className="py-5">
            <SignaturePad
              readOnly
              onChange={() => {}}
              value={signatureValueFrom(page.sorento_signature)}
              hideLocation
              requestGeolocation={false}
              label={preparedBy ?? 'Signature'}
            />
          </CardContent>
        </Card>

        <div className="min-w-0">
          <CustomerSignature
            page={page}
            token={token}
            signerName={signerName}
            onSignerName={setSignerName}
          />
        </div>
      </div>
    </PageShell>
  );
}
