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

function PortalVerifyContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

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
        setError(e instanceof Error ? e.message : 'Failed to send code.');
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
        if (!otpFiredRef.current) {
          otpFiredRef.current = true;
          await sendCode(info.contact_id, info.space_id, { silent: true });
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
      toast.success('Verified.');
      router.replace('/portal');
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
            <AlertTitle>Your portal session expired. Verify with an OTP to continue.</AlertTitle>
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
              Resend code
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
