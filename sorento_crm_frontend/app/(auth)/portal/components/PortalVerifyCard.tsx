'use client';

/**
 * Shared OTP verification card for both portal trees:
 *
 * - slug mode (`/portal/c/{slug}/verify`): identity comes from the stable
 *   slug via fetchSlugInfo - no token required at all.
 * - token mode (`/portal/verify`): legacy flow - identity recovered from the
 *   (possibly expired) token via fetchTokenInfo.
 *
 * Always renders the WhatsApp escape hatch: OTP delivery is fire-and-forget
 * (Respond.io accepts the send even when the 24h customer-service window is
 * closed and the message silently fails), so the user can always reopen the
 * window by messaging the business first, then tap Resend.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { AlertCircle, MessageCircle } from 'lucide-react';
import { toast } from '@/lib/toast';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  clearPortalToken,
  fetchSlugInfo,
  fetchTokenInfo,
  readPortalToken,
  requestOtp,
  verifyOtp,
  writePortalToken,
} from '../lib/portal-client';
import { isSubmissionKind } from '../lib/portal-client';
import {
  clearPortalSlug,
  portalDetailPath,
  portalHomePath,
  waMeUrl,
  writePortalSlug,
} from '../lib/portal-paths';

const SENT_KEY_PREFIX = 'sorento.portal.otpSent.';
const RESEND_COOLDOWN_S = 60;

// Human labels for the submission kind passed via ?type= on deep-link verify
// redirects, used in the "This {label} belongs to …" confirm copy.
const TYPE_LABELS: Record<string, string> = {
  complaint: 'complaint',
  stock_inquiry: 'stock inquiry',
  purchase_request: 'purchase request',
  sponsorship_form: 'sponsorship form',
};

// One prefill for both WhatsApp CTAs (escape hatch + link request) so the
// agent/n8n side only has to recognize a single message.
const WA_TEXT = 'Hi, I need my portal link.';

interface Props {
  /** Stable contact slug - present on the slug tree, absent on legacy. */
  slug?: string;
}

type CardState =
  | 'loading' // resolving slug-info / token-info
  | 'confirm-identity' // deep link on a new device - confirm "log in with this number?"
  | 'otp' // normal verify flow
  | 'unknown-slug' // slug-info 404 - ask for a fresh portal link
  | 'request-link' // "Not your number?" - ask for own portal link
  | 'lookup-failed'; // transient slug-info/token-info failure - offer retry

export function PortalVerifyCard({ slug }: Props) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const reason = searchParams?.get('reason');
  const isLogout = reason === 'logout';
  // Submission kind from the deep-link verify redirect - its presence means the
  // user followed a link to a specific form on a device with no session, so we
  // gate on an explicit "log in with this number?" confirmation before sending
  // a code (instead of silently auto-firing).
  const entityType = searchParams?.get('type') || null;
  const entityLabel = entityType ? TYPE_LABELS[entityType] ?? 'form' : null;

  const [state, setState] = useState<CardState>('loading');
  const [contactId, setContactId] = useState<string | null>(null);
  const [spaceId, setSpaceId] = useState<string | null>(null);
  const [contactName, setContactName] = useState<string | null>(null);
  const [maskedPhone, setMaskedPhone] = useState<string | null>(null);
  const [whatsappNumber, setWhatsappNumber] = useState<string | null>(null);
  const [code, setCode] = useState('');
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cooldown, setCooldown] = useState(0);
  const otpFiredRef = useRef(false);
  const lastAutoVerifiedRef = useRef<string | null>(null);

  // Resend cooldown ticker.
  useEffect(() => {
    if (cooldown <= 0) return;
    const t = window.setTimeout(() => setCooldown((c) => c - 1), 1000);
    return () => window.clearTimeout(t);
  }, [cooldown]);

  const sendCode = useCallback(
    async (cid: string, sid: string, opts: { silent?: boolean } = {}): Promise<boolean> => {
      setPending(true);
      try {
        const result = await requestOtp(cid, sid);
        setSentTo(result.sent_to);
        setCooldown(RESEND_COOLDOWN_S);
        if (!opts.silent) toast.success('Verification code sent.');
        setError(null);
        return true;
      } catch (e) {
        const msg = e instanceof Error ? e.message : 'Failed to send code.';
        // On silent auto-fire, ignore "please wait" cooldown errors - the
        // previous code is presumably still valid and the user has it.
        if (opts.silent && /please wait/i.test(msg)) {
          setSentTo((prev) => prev ?? 'your registered contact');
          setCooldown(RESEND_COOLDOWN_S);
          return true;
        }
        setError(msg);
        return false;
      } finally {
        setPending(false);
      }
    },
    [],
  );

  // Bootstrap: resolve identity from slug (slug tree) or token (legacy),
  // then auto-fire the OTP unless the user just logged out.
  useEffect(() => {
    let cancelled = false;

    const autoFire = async (cid: string, sid: string, guardKey: string) => {
      const reasonNow = searchParams?.get('reason');
      if (reasonNow === 'logout') return;
      const sentKey = SENT_KEY_PREFIX + guardKey;
      const alreadyFired =
        typeof window !== 'undefined' && window.sessionStorage.getItem(sentKey) === '1';
      if (!otpFiredRef.current && !alreadyFired) {
        otpFiredRef.current = true;
        const sent = await sendCode(cid, sid, { silent: true });
        // Persist the guard ONLY after a successful dispatch - a failed send
        // must not advertise a phantom "code sent" on the next reload.
        if (sent && typeof window !== 'undefined') {
          window.sessionStorage.setItem(sentKey, '1');
        }
      } else if (alreadyFired) {
        setSentTo((prev) => prev ?? 'your registered contact');
      }
    };

    (async () => {
      try {
        if (slug) {
          const info = await fetchSlugInfo(slug);
          if (cancelled) return;
          if (!info) {
            setState('unknown-slug');
            return;
          }
          setContactId(info.contact_id);
          setSpaceId(info.space_id);
          setContactName(info.name ?? null);
          setMaskedPhone(info.masked_phone);
          setWhatsappNumber(info.whatsapp_number);
          // Deep link → confirm identity before sending. Otherwise auto-fire.
          if (entityType) {
            setState('confirm-identity');
            return;
          }
          setState('otp');
          await autoFire(info.contact_id, info.space_id, slug);
          return;
        }
        // Legacy token mode.
        const urlToken = searchParams?.get('token');
        const token = (urlToken && urlToken.trim()) || readPortalToken();
        if (!token) {
          setState('request-link');
          return;
        }
        const info = await fetchTokenInfo(token);
        if (cancelled) return;
        setContactId(info.contact_id);
        setSpaceId(info.space_id);
        setContactName(info.name ?? null);
        setMaskedPhone(info.masked_phone ?? null);
        setWhatsappNumber(info.whatsapp_number ?? null);
        if (entityType) {
          setState('confirm-identity');
          return;
        }
        setState('otp');
        await autoFire(info.contact_id, info.space_id, token);
      } catch (e) {
        if (cancelled) return;
        // Transient lookup failure (5xx / network): the OTP form would be a
        // dead end (no contact resolved, no wa.me number) - render an explicit
        // retry card instead.
        setState('lookup-failed');
        setError(e instanceof Error ? e.message : 'Could not look up portal session.');
      }
    })();

    return () => {
      cancelled = true;
    };
    // Intentional: only on first mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleResend = useCallback(() => {
    if (!contactId || !spaceId) return;
    void sendCode(contactId, spaceId);
  }, [contactId, spaceId, sendCode]);

  // Confirm-identity → send the first code, then drop into the OTP entry card.
  const handleConfirmIdentity = useCallback(async () => {
    if (!contactId || !spaceId) return;
    setState('otp');
    const sent = await sendCode(contactId, spaceId);
    if (sent && slug && typeof window !== 'undefined') {
      window.sessionStorage.setItem(SENT_KEY_PREFIX + slug, '1');
    }
  }, [contactId, spaceId, sendCode, slug]);

  const handleVerify = useCallback(async () => {
    setError(null);
    if (!contactId || !spaceId) {
      setError('Missing portal context.');
      return;
    }
    if (!code.trim()) {
      setError('Enter the verification code.');
      return;
    }
    setPending(true);
    try {
      const result = await verifyOtp(contactId, spaceId, code.trim());
      writePortalToken(result.token);
      if (slug) writePortalSlug(slug);
      if (typeof window !== 'undefined') {
        window.sessionStorage.setItem('sorento.portalTokenWrittenAt', String(Date.now()));
        Object.keys(window.sessionStorage)
          .filter((k) => k.startsWith(SENT_KEY_PREFIX))
          .forEach((k) => window.sessionStorage.removeItem(k));
      }
      toast.success('Verified.');
      const desiredType = searchParams?.get('type');
      const desiredId = searchParams?.get('id');
      // Deep link → land back on that exact form. Otherwise the type index /
      // portal home. Slug tree keeps the stable URL; legacy /portal resolves the
      // slug and redirects, keeping the address bar bookmarkable.
      const target =
        desiredId && desiredType && isSubmissionKind(desiredType)
          ? portalDetailPath(desiredType, desiredId, slug ?? null)
          : portalHomePath({ slug: slug ?? null, type: desiredType });
      // Hard-navigate so the fresh storage values are guaranteed visible.
      if (typeof window !== 'undefined') {
        window.location.assign(target);
      } else {
        router.replace(target);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to verify.');
    } finally {
      setPending(false);
    }
  }, [code, contactId, router, searchParams, slug, spaceId]);

  useEffect(() => {
    const trimmed = code.trim();
    if (trimmed.length !== 6) return;
    if (pending || state !== 'otp') return;
    if (!contactId || !spaceId || !sentTo) return;
    if (lastAutoVerifiedRef.current === trimmed) return;
    lastAutoVerifiedRef.current = trimmed;
    void handleVerify();
  }, [code, pending, state, contactId, spaceId, sentTo, handleVerify]);

  if (state === 'loading') {
    return (
      <VerifyShell>
        <p className="text-sm text-muted-foreground">Looking up your portal session...</p>
      </VerifyShell>
    );
  }

  if (state === 'lookup-failed') {
    return (
      <VerifyShell title="Something went wrong">
        <Alert variant="destructive">
          <AlertIcon>
            <AlertCircle />
          </AlertIcon>
          <AlertTitle>{error || 'Could not look up your portal session.'}</AlertTitle>
        </Alert>
        <p className="text-sm text-muted-foreground">
          This is usually temporary. Try again in a moment.
        </p>
        <Button
          type="button"
          className="h-11 w-full"
          onClick={() => window.location.reload()}
          data-testid="lookup-retry"
        >
          Try again
        </Button>
      </VerifyShell>
    );
  }

  if (state === 'confirm-identity') {
    const who = contactName || maskedPhone || 'this contact';
    return (
      <VerifyShell title="Confirm your identity">
        <Alert>
          <AlertIcon>
            <AlertCircle />
          </AlertIcon>
          <AlertTitle>
            This {entityLabel} belongs to{' '}
            <span className="font-semibold whitespace-nowrap">{who}</span>
            {contactName && maskedPhone ? (
              <span className="font-normal"> ({maskedPhone})</span>
            ) : null}
            .
          </AlertTitle>
        </Alert>
        <p className="text-sm text-muted-foreground">
          To open it, log in with this number. We&apos;ll send a one-time code to
          the WhatsApp{maskedPhone ? ` ${maskedPhone}` : ''} on file.
        </p>
        <Button
          type="button"
          className="h-11 w-full"
          onClick={handleConfirmIdentity}
          disabled={pending || !contactId || !spaceId}
          data-testid="confirm-identity-send"
        >
          Log in with this number
        </Button>

        {/* wa.me fallback - kept secondary per product decision. */}
        {whatsappNumber && (
          <div className="rounded-lg border bg-muted/40 px-3 py-3 space-y-2">
            <p className="text-xs text-muted-foreground">
              Not your number, or need a different link? Message us on WhatsApp.
            </p>
            <Button asChild variant="outline" size="sm" className="h-9 w-full">
              <a
                href={waMeUrl(whatsappNumber, WA_TEXT)}
                target="_blank"
                rel="noopener noreferrer"
              >
                <MessageCircle className="h-4 w-4 mr-2" />
                Message us on WhatsApp
              </a>
            </Button>
          </div>
        )}
      </VerifyShell>
    );
  }

  if (state === 'unknown-slug' || state === 'request-link') {
    return (
      <VerifyShell title="Get your portal link">
        <Alert>
          <AlertIcon>
            <AlertCircle />
          </AlertIcon>
          <AlertTitle>
            {state === 'unknown-slug'
              ? 'This portal link is not recognized.'
              : 'No portal session on this device.'}
          </AlertTitle>
        </Alert>
        {whatsappNumber ? (
          <>
            <p className="text-sm text-muted-foreground">
              Message us on WhatsApp and we will send you your personal portal link.
            </p>
            <Button asChild className="h-11 w-full" data-testid="wa-request-link">
              <a
                href={waMeUrl(whatsappNumber, WA_TEXT)}
                target="_blank"
                rel="noopener noreferrer"
              >
                <MessageCircle className="h-4 w-4 mr-2" />
                Message us on WhatsApp
              </a>
            </Button>
          </>
        ) : (
          <p className="text-sm text-muted-foreground">
            Contact us on WhatsApp and we will send you your personal portal link.
          </p>
        )}
      </VerifyShell>
    );
  }

  return (
    <VerifyShell title="Verify your identity">
      <Alert>
        <AlertIcon>
          <AlertCircle />
        </AlertIcon>
        <AlertTitle>
          {isLogout
            ? 'You have been logged out. Verify with an OTP to continue.'
            : 'Verify with a one-time code to open your portal.'}
        </AlertTitle>
      </Alert>

      {maskedPhone && (
        <p className="text-sm">
          We&apos;ll send a code to your WhatsApp{' '}
          <span className="font-medium whitespace-nowrap">{maskedPhone}</span>
        </p>
      )}

      {sentTo && (
        <p className="text-xs text-muted-foreground">
          Code sent{maskedPhone ? '' : ` to ${sentTo}`}. It expires in 10 minutes.
          Please do not share it with anyone.
        </p>
      )}

      <div className="space-y-1.5">
        <Label htmlFor="code">Verification code</Label>
        <Input
          variant="lg"
          id="code"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          inputMode="numeric"
          maxLength={6}
          placeholder="6-digit code"
          autoComplete="one-time-code"
          disabled={!contactId || !spaceId}
          className="text-center tracking-[0.4em] text-lg font-medium"
        />
      </div>

      <div className="flex flex-col-reverse sm:flex-row gap-2">
        <Button
          type="button"
          variant="outline"
          onClick={handleResend}
          disabled={pending || !contactId || !spaceId || cooldown > 0}
          className="h-11 w-full sm:w-auto"
        >
          {cooldown > 0
            ? `Resend in ${cooldown}s`
            : sentTo
              ? 'Resend code'
              : 'Send code'}
        </Button>
        <Button
          type="button"
          onClick={handleVerify}
          disabled={pending || !sentTo}
          className="h-11 w-full sm:flex-1"
        >
          Verify and continue
        </Button>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertIcon>
            <AlertCircle />
          </AlertIcon>
          <AlertTitle>{error}</AlertTitle>
        </Alert>
      )}

      {/* WhatsApp escape hatch - always visible when the business number is
          configured. Delivery is fire-and-forget, so when the 24h window is
          closed the code never arrives; messaging the business first reopens
          the window, then Resend delivers. */}
      {whatsappNumber && (
        <div
          className="rounded-lg border bg-muted/40 px-3 py-3 space-y-2"
          data-testid="wa-escape-hatch"
        >
          <p className="text-xs text-muted-foreground">
            No code after a minute? WhatsApp sometimes blocks messages from us until
            you message first. Send us any message, then tap Resend.
          </p>
          <Button asChild variant="outline" size="sm" className="h-9 w-full">
            <a
              href={waMeUrl(whatsappNumber, WA_TEXT)}
              target="_blank"
              rel="noopener noreferrer"
            >
              <MessageCircle className="h-4 w-4 mr-2" />
              Message us on WhatsApp
            </a>
          </Button>
        </div>
      )}

      {slug && (
        <button
          type="button"
          onClick={() => {
            // Wrong identity on this device - drop the stored slug + token so
            // the next visit starts clean, then point at the link-request CTA.
            clearPortalToken();
            clearPortalSlug();
            setState('request-link');
          }}
          className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
          data-testid="not-your-number"
        >
          Not your number?
        </button>
      )}
    </VerifyShell>
  );
}

function VerifyShell({
  title,
  children,
}: {
  title?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen max-w-md mx-auto px-4 py-6 space-y-4">
      <Card>
        {title && (
          <CardHeader>
            <CardTitle>{title}</CardTitle>
          </CardHeader>
        )}
        <CardContent className="space-y-4">{children}</CardContent>
      </Card>
    </div>
  );
}
