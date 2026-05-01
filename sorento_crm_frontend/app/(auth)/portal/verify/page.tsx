'use client';

import { Suspense, useCallback, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { AlertCircle } from 'lucide-react';
import { toast } from 'sonner';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { requestOtp, verifyOtp, writePortalToken } from '../lib/portal-client';

function PortalVerifyContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const reason = searchParams?.get('reason');
  const initialContact = searchParams?.get('contact_id') ?? '';
  const initialSpace = searchParams?.get('space_id') ?? '';

  const [contactId, setContactId] = useState(initialContact);
  const [spaceId, setSpaceId] = useState(initialSpace);
  const [code, setCode] = useState('');
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSendCode = useCallback(async () => {
    setError(null);
    if (!contactId.trim() || !spaceId.trim()) {
      setError('Contact and space are required.');
      return;
    }
    setPending(true);
    try {
      const result = await requestOtp(contactId.trim(), spaceId.trim());
      setSentTo(result.sent_to);
      toast.success('Verification code sent.');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to send code.');
    } finally {
      setPending(false);
    }
  }, [contactId, spaceId]);

  const handleVerify = useCallback(async () => {
    setError(null);
    if (!code.trim()) {
      setError('Enter the verification code.');
      return;
    }
    setPending(true);
    try {
      const result = await verifyOtp(contactId.trim(), spaceId.trim(), code.trim());
      writePortalToken(result.token);
      toast.success('Verified.');
      router.replace('/portal');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to verify.');
    } finally {
      setPending(false);
    }
  }, [code, contactId, router, spaceId]);

  useEffect(() => {
    // If contact + space arrived in the URL, kick off the OTP send immediately.
    if (initialContact && initialSpace && !sentTo) {
      void handleSendCode();
    }
    // Intentional: only on first mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="min-h-screen max-w-md mx-auto px-4 py-6 space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Verify your identity</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {reason === 'expired' && (
            <Alert>
              <AlertIcon>
                <AlertCircle />
              </AlertIcon>
              <AlertTitle>Your portal session expired. Verify with an OTP to continue.</AlertTitle>
            </Alert>
          )}
          <div className="space-y-1.5">
            <Label htmlFor="contact_id">Contact ID</Label>
            <Input
              id="contact_id"
              value={contactId}
              onChange={(e) => setContactId(e.target.value)}
              autoComplete="off"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="space_id">Space ID</Label>
            <Input
              id="space_id"
              value={spaceId}
              onChange={(e) => setSpaceId(e.target.value)}
              autoComplete="off"
            />
          </div>
          <Button type="button" onClick={handleSendCode} disabled={pending}>
            {sentTo ? 'Resend code' : 'Send verification code'}
          </Button>
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
            />
          </div>
          <Button type="button" onClick={handleVerify} disabled={pending || !sentTo}>
            Verify and continue
          </Button>
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
