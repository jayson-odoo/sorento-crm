'use client';

/**
 * Shared OTP verification card for both portal trees:
 *
 * - slug mode (`/portal/c/{slug}/verify`): identity comes from the stable
 *   slug via fetchSlugInfo - no token required at all.
 * - token mode (`/portal/verify`): legacy flow - identity recovered from the
 *   (possibly expired) token via fetchTokenInfo.
 *
 * Minimal card per r8 D-V1: masked-number line, "Not your number?" directly
 * under it, the code input, and a single Send / Resend button. Nothing is sent
 * until the user presses it (SIGNIN-2FA-NOT-ROLE AC-10). The sixth digit
 * verifies automatically; no separate "Verify and continue" button and no
 * WhatsApp escape hatch on this card (recovery is Resend only).
 */

import { useCallback, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { getSession } from 'next-auth/react';
import { AlertCircle, MessageCircle } from 'lucide-react';
import { toast } from '@/lib/toast';
import { impersonationStore, useImpersonationSession } from '@/lib/impersonation-store';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { OtpCodeField, useResendCooldown } from '@/components/auth/OtpCodeField';
import {
  clearPortalToken,
  fetchSlugInfo,
  fetchTokenInfo,
  openCrmSession,
  readPortalToken,
  requestOtp,
  verifyOtp,
  writePortalToken,
} from '../lib/portal-client';
import { hasPortalDetailPage } from '@/lib/portal-form-kinds';
import {
  clearPortalSlug,
  crmPathForPortalPath,
  portalDetailPath,
  portalHomePath,
  waMeUrl,
  writePortalSlug,
} from '../lib/portal-paths';
import { sessionStore } from '@/lib/storage';

/** The CRM home the fresh session names when it is a salesperson's (`/my-requests`), else null. */
async function salespersonHomePath(): Promise<string | null> {
  try {
    const session = await getSession();
    const home = (session?.user as { homePath?: unknown } | undefined)?.homePath;
    return typeof home === 'string' && home.startsWith('/my-requests') ? home : null;
  } catch {
    return null;
  }
}

const RESEND_COOLDOWN_S = 60;

// Human labels for the submission kind passed via ?type= on deep-link verify
// redirects, used in the "This {label} belongs to …" confirm copy.
const TYPE_LABELS: Record<string, string> = {
  complaint: 'complaint',
  stock_inquiry: 'stock inquiry',
  purchase_request: 'purchase request',
  sponsorship_form: 'sponsorship form',
  project_registration: 'project registration',
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
  // Viewing as the salesperson: "Not your number?" would clear the admin's own device sign-in.
  const viewingAs = useImpersonationSession() !== null;
  const reason = searchParams?.get('reason');
  const isLogout = reason === 'logout';
  // Submission kind from the deep-link verify redirect - its presence means the
  // user followed a link to a specific form on a device with no session, so we
  // gate on an explicit "log in with this number?" confirmation before sending
  // a code.
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
  const [cooldown, setCooldown] = useResendCooldown();

  const sendCode = useCallback(
    async (cid: string, sid: string): Promise<boolean> => {
      setPending(true);
      try {
        const result = await requestOtp(cid, sid);
        setSentTo(result.sent_to);
        setCooldown(RESEND_COOLDOWN_S);
        toast.success('Verification code sent.');
        setError(null);
        return true;
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to send code.');
        return false;
      } finally {
        setPending(false);
      }
    },
    [setCooldown],
  );

  // Bootstrap: resolve identity from slug (slug tree) or token (legacy). No
  // code goes on mount: the user presses Send code (SIGNIN-2FA-NOT-ROLE AC-10).
  useEffect(() => {
    let cancelled = false;

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
          // Deep link → confirm identity before sending.
          setState(entityType ? 'confirm-identity' : 'otp');
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
        setState(entityType ? 'confirm-identity' : 'otp');
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
    await sendCode(contactId, spaceId);
  }, [contactId, spaceId, sendCode]);

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
      // An admin viewing as the salesperson (CRM impersonation): the token is this tab's only, the
      // device's stored token and slug and the admin's CRM session are never replaced.
      const viewingAs = impersonationStore.getState() !== null;
      writePortalToken(result.token, { impersonation: viewingAs });
      if (slug && !viewingAs) writePortalSlug(slug);
      // A contact with a CRM user also gets a CRM session (PORTAL-P1-SESSION-LINK).
      // Before navigating, so the NextAuth cookie is set when the page is left.
      let crmHome: string | null = viewingAs ? '/my-requests' : null;
      if (
        !viewingAs &&
        result.portal_link_secret &&
        (await openCrmSession(result.portal_link_secret))
      ) {
        crmHome = await salespersonHomePath();
      }
      if (typeof window !== 'undefined') {
        sessionStore.setItem('sorento.portalTokenWrittenAt', String(Date.now()));
      }
      toast.success('Verified.');
      const desiredType = searchParams?.get('type');
      const desiredId = searchParams?.get('id');
      // Deep link → land back on that exact form. Otherwise the type index /
      // portal home. Slug tree keeps the stable URL; legacy /portal resolves the
      // slug and redirects, keeping the address bar bookmarkable.
      // A salesperson lands in the CRM shell instead (PORTAL-P3-ROLE-MENU).
      const portalTarget =
        desiredId && desiredType && hasPortalDetailPage(desiredType)
          ? portalDetailPath(desiredType, desiredId, slug ?? null)
          : portalHomePath({ slug: slug ?? null, type: desiredType });
      // Already under /my-requests when this card runs inside the CRM verify page.
      const target = crmHome
        ? portalTarget.startsWith('/my-requests')
          ? portalTarget
          : (crmPathForPortalPath(portalTarget) ?? '/my-requests')
        : portalTarget;
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
      {isLogout && (
        <Alert>
          <AlertIcon>
            <AlertCircle />
          </AlertIcon>
          <AlertTitle>You have been logged out. Verify with an OTP to continue.</AlertTitle>
        </Alert>
      )}

      {maskedPhone && (
        <p className="text-sm">
          We&apos;ll send a code to your WhatsApp{' '}
          <span className="font-medium whitespace-nowrap">{maskedPhone}</span>
        </p>
      )}

      {slug && !viewingAs && (
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

      <OtpCodeField
        id="code"
        value={code}
        onChange={setCode}
        onComplete={() => void handleVerify()}
        cooldown={cooldown}
        sent={Boolean(sentTo)}
        pending={pending}
        disabled={!contactId || !spaceId}
        onResend={handleResend}
        primarySend
      />

      {error && (
        <Alert variant="destructive">
          <AlertIcon>
            <AlertCircle />
          </AlertIcon>
          <AlertTitle>{error}</AlertTitle>
        </Alert>
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
    // M6-02: dvh - phone-facing (verify/OTP), so a `vh` shell that sits under
    // mobile Safari's dynamic toolbar clips the card the reader is filling in.
    <div className="min-h-dvh max-w-md mx-auto px-4 py-6 space-y-4">
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
