'use client';

import { Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { AlertCircle } from 'lucide-react';
import { toast } from 'sonner';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  fetchTokenInfo,
  readPortalToken,
  requestOtp,
  verifyOtp,
  writePortalToken,
} from '../lib/portal-client';

const SENT_KEY_PREFIX = 'sorento.portal.otpSent.';

function PortalVerifyContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const reason = searchParams?.get('reason');
  const isLogout = reason === 'logout';

  const [contactId, setContactId] = useState<string | null>(null);
  const [spaceId, setSpaceId] = useState<string | null>(null);
  const [code, setCode] = useState('');
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [bootstrapping, setBootstrapping] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const otpFiredRef = useRef(false);

  const sendCode = useCallback(
    async (cid: string, sid: string, opts: { silent?: boolean } = {}) => {
      setPending(true);
      try {
        const result = await requestOtp(cid, sid);
        setSentTo(result.sent_to);
        if (!opts.silent) toast.success('Verification code sent.');
        setError(null);
      } catch (e) {
        const msg = e instanceof Error ? e.message : 'Failed to send code.';
        // On silent auto-fire, ignore "please wait" cooldown errors — the
        // previous code is presumably still valid and the user has it. Mark
        // sentTo so the verify button enables and don't surface a destructive
        // alert that would obscure a successful manual verify a second later.
        if (opts.silent && /please wait/i.test(msg)) {
          setSentTo((prev) => prev ?? 'your registered contact');
          return;
        }
        setError(msg);
      } finally {
        setPending(false);
      }
    },
    [],
  );

  // Bootstrap: read token from sessionStorage or ?token= URL param, look up
  // the (contact_id, space_id) pair from the BE, then auto-fire OTP.
  useEffect(() => {
    let cancelled = false;
    const urlToken = searchParams?.get('token');
    const token = (urlToken && urlToken.trim()) || readPortalToken();

    if (!token) {
      setBootstrapping(false);
      setError('No portal token. Please request a new link.');
      return;
    }

    (async () => {
      try {
        const info = await fetchTokenInfo(token);
        if (cancelled) return;
        setContactId(info.contact_id);
        setSpaceId(info.space_id);
        setBootstrapping(false);
        // Skip auto-fire when the user explicitly logged out — they did not
        // ask to log in again, so don't burn an OTP. They can click
        // "Send code" / "Resend code" when ready.
        const reasonNow = searchParams?.get('reason');
        if (reasonNow === 'logout') {
          return;
        }
        // Guard the auto-fire against React StrictMode double-invoke AND
        // against component re-mounts within the same browser session
        // (e.g. Suspense boundary toggling, /portal -> /portal/verify
        // bouncing on a transient 401). The sessionStorage key is keyed by
        // token so a brand-new portal link will still auto-fire once.
        const sentKey = SENT_KEY_PREFIX + token;
        const alreadyFired =
          typeof window !== 'undefined' &&
          window.sessionStorage.getItem(sentKey) === '1';
        if (!otpFiredRef.current && !alreadyFired) {
          otpFiredRef.current = true;
          if (typeof window !== 'undefined') {
            window.sessionStorage.setItem(sentKey, '1');
          }
          await sendCode(info.contact_id, info.space_id, { silent: true });
        } else if (alreadyFired) {
          // Mirror the post-send hint so the verify button enables without
          // hammering the BE again.
          setSentTo((prev) => prev ?? 'your registered contact');
        }
      } catch (e) {
        if (cancelled) return;
        setBootstrapping(false);
        setError(e instanceof Error ? e.message : 'Could not look up portal token.');
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
      // Stamp when the fresh token was written so /portal can grace-period a
      // transient 401 instead of bouncing right back here.
      if (typeof window !== 'undefined') {
        window.sessionStorage.setItem(
          'sorento.portalTokenWrittenAt',
          String(Date.now()),
        );
        // Drop any silent-fire guards from the previous expired-token session
        // so a future /portal/verify visit (different token) can re-fire OTP.
        Object.keys(window.sessionStorage)
          .filter((k) => k.startsWith(SENT_KEY_PREFIX))
          .forEach((k) => window.sessionStorage.removeItem(k));
      }
      toast.success('Verified.');
      // Hard-navigate so the app-router transition cannot stall and the new
      // sessionStorage value is guaranteed visible to the fresh /portal mount.
      if (typeof window !== 'undefined') {
        window.location.assign('/portal');
      } else {
        router.replace('/portal');
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to verify.');
    } finally {
      setPending(false);
    }
  }, [code, contactId, router, spaceId]);

  return (
    <div className="min-h-screen max-w-md mx-auto px-4 py-6 space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Verify your identity</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <Alert>
            <AlertIcon>
              <AlertCircle />
            </AlertIcon>
            <AlertTitle>
              {isLogout
                ? 'You have been logged out. Verify with an OTP to continue.'
                : 'Your portal session expired. Verify with an OTP to continue.'}
            </AlertTitle>
          </Alert>

          {bootstrapping && (
            <p className="text-sm text-muted-foreground">Looking up your portal session...</p>
          )}

          {sentTo && (
            <p className="text-xs text-muted-foreground">
              Code sent to {sentTo}. It expires in 10 minutes.
            </p>
          )}

          <div className="space-y-1.5">
            <Label htmlFor="code">Verification code</Label>
            <Input
              id="code"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              inputMode="numeric"
              maxLength={6}
              placeholder="6-digit code"
              autoComplete="one-time-code"
              disabled={bootstrapping || !contactId || !spaceId}
            />
          </div>

          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={handleResend}
              disabled={pending || bootstrapping || !contactId || !spaceId}
            >
              {sentTo ? 'Resend code' : 'Send code'}
            </Button>
            <Button
              type="button"
              onClick={handleVerify}
              disabled={pending || bootstrapping || !sentTo}
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
        </CardContent>
      </Card>
    </div>
  );
}

export default function PortalVerifyPage() {
  return (
    <Suspense fallback={null}>
      <PortalVerifyContent />
    </Suspense>
  );
}
