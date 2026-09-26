'use client';

/**
 * `/signin`'s Phone tab (PLAN-unified-identity-26sep.md S1, AC-20 to AC-25,
 * AC-29). Step 1 asks for the number and requests a code; step 2 reuses the
 * portal's shared `OtpCodeField` and signs in on the sixth digit through
 * NextAuth's `phone-otp` Credentials provider - the same shape the Email tab
 * gets from `signIn('credentials', ...)`.
 *
 * The page owns the one destructive `Alert` under the toggle (AC-20/AC-29):
 * this component reports errors up via `onError` rather than rendering its
 * own, so switching tabs clears the same slot the Email form uses.
 */

import { useState } from 'react';
import { signIn } from 'next-auth/react';
import { LoaderCircleIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { OtpCodeField, useResendCooldown } from '@/components/auth/OtpCodeField';
import { mockVerifyError } from '@/services/phoneSigninService';
import { useRequestSigninCode } from '../hooks/usePhoneSignin';

type PhoneStep = 'phone' | 'code';

interface Props {
  onError: (message: string | null) => void;
  /** Called once a phone sign-in succeeds - the page runs the same landing logic as Email. */
  onSignedIn: () => void;
}

export function PhoneSignIn({ onError, onSignedIn }: Props) {
  const [step, setStep] = useState<PhoneStep>('phone');
  const [phone, setPhone] = useState('');
  const [code, setCode] = useState('');
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [cooldown, setCooldown] = useResendCooldown();

  const requestCode = useRequestSigninCode();

  const sendCode = () => {
    onError(null);
    requestCode.mutate(phone, {
      onSuccess: (result) => {
        setSentTo(result.sent_to);
        setCooldown(result.resend_in_seconds);
        setStep('code');
      },
      onError: (err) => onError(err.message),
    });
  };

  const handleChangeNumber = () => {
    onError(null);
    setStep('phone');
    setCode('');
    setSentTo(null);
    setCooldown(0);
  };

  const handleVerify = async (typedCode: string) => {
    onError(null);

    // Phase 1 mock only: lets the error states be tuned without a backend -
    // see services/phoneSigninService.ts.
    const mockError = mockVerifyError(typedCode);
    if (mockError) {
      onError(mockError);
      setCode('');
      return;
    }

    setVerifying(true);
    try {
      const response = await signIn('phone-otp', {
        redirect: false,
        phone,
        code: typedCode,
      });

      if (response?.error) {
        let message = response.error || 'An error occurred during sign in.';
        try {
          const errorData = JSON.parse(response.error);
          message = errorData.message || message;
        } catch {
          // Not JSON - use the raw error as-is.
        }
        onError(message);
        setCode('');
        return;
      }

      onSignedIn();
    } catch (err) {
      onError(
        err instanceof Error
          ? err.message
          : 'An unexpected error occurred. Please try again.',
      );
    } finally {
      setVerifying(false);
    }
  };

  if (step === 'code') {
    return (
      <div className="space-y-5">
        <p className="text-sm">
          We&apos;ll send a code to your WhatsApp{' '}
          <span className="font-medium whitespace-nowrap">{sentTo}</span>{' '}
          <button
            type="button"
            onClick={handleChangeNumber}
            className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
          >
            Change number
          </button>
        </p>

        <OtpCodeField
          id="phone-signin-code"
          value={code}
          onChange={setCode}
          onComplete={(value) => void handleVerify(value)}
          cooldown={cooldown}
          sent={Boolean(sentTo)}
          pending={verifying || requestCode.isPending}
          onResend={sendCode}
          autoFocus
        />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="space-y-1.5">
        <Label htmlFor="phone">Phone number</Label>
        <Input
          id="phone"
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          inputMode="tel"
          autoComplete="tel"
          placeholder="e.g. 012-345 6789"
        />
      </div>

      <Button
        type="button"
        onClick={sendCode}
        disabled={requestCode.isPending || !phone.trim()}
        className="w-full"
      >
        {requestCode.isPending ? (
          <LoaderCircleIcon className="size-4 animate-spin" />
        ) : null}
        Continue
      </Button>
    </div>
  );
}
