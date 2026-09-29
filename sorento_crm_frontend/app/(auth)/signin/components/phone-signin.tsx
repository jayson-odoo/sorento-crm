'use client';

/**
 * `/signin`'s phone flow (PLAN-unified-identity-26sep.md S1, AC-20 to AC-25,
 * AC-29). Step 1 asks for the number and requests a code; step 2 reuses the
 * portal's shared `OtpCodeField` and signs in on the sixth digit through
 * NextAuth's `phone-otp` Credentials provider - the same shape the email form
 * gets from `signIn('credentials', ...)`.
 *
 * The page opens it from the round phone button under "or Log in with" and
 * owns the one destructive `Alert` above it (AC-20/AC-29): this component
 * reports errors up via `onError` rather than rendering its own, so "Back to
 * email" clears the same slot the email form uses.
 *
 * The number is entered through the shared `PhoneInput` (owner ruling, 29 Sep
 * 2026): Malaysia by default, sent as E.164, and an incomplete number stops at
 * the field's own error state instead of reaching request-code.
 *
 * From the sixth digit to the destination's first paint the card never looks
 * idle (fix round 4, #1307): the field locks and "Signing you in" takes the
 * resend button's place, and a successful sign-in leaves it that way through
 * the session read and the route change - this component unmounts when the
 * destination renders, so there is nothing to reset. Only a failure unlocks
 * the field, cleared and focused for the retry.
 */

import { useState } from 'react';
import { signIn } from 'next-auth/react';
import { LoaderCircleIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { PhoneInput } from '@/components/common/PhoneInput';
import { Label } from '@/components/ui/label';
import {
  OtpCodeField,
  useResendCooldown,
} from '@/components/auth/OtpCodeField';
import { useRequestSigninCode } from '../hooks/usePhoneSignin';

type PhoneStep = 'phone' | 'code';

interface Props {
  onError: (message: string | null) => void;
  /**
   * Called once a phone sign-in succeeds - the page runs the same landing
   * logic as Email. Awaited, so a failure there still unlocks the field.
   */
  onSignedIn: () => Promise<void> | void;
  /** Mirrors the verifying state so the page can lock "Back to email" too. */
  onBusyChange?: (busy: boolean) => void;
}

export function PhoneSignIn({ onError, onSignedIn, onBusyChange }: Props) {
  const [step, setStep] = useState<PhoneStep>('phone');
  const [phone, setPhone] = useState('');
  const [phoneValid, setPhoneValid] = useState(false);
  const [showPhoneError, setShowPhoneError] = useState(false);
  const [code, setCode] = useState('');
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [cooldown, setCooldown] = useResendCooldown();

  const requestCode = useRequestSigninCode();

  // The page's copy is set in the same batch as ours, never from an effect:
  // an effect lands one commit later, so for that commit the field is back
  // but "Back to email" is still locked (fix round 5, #1307).
  const setBusy = (busy: boolean) => {
    setVerifying(busy);
    onBusyChange?.(busy);
  };

  const sendCode = () => {
    onError(null);
    if (!phoneValid) {
      setShowPhoneError(true);
      return;
    }
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
    setBusy(true);
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
        setBusy(false);
        return;
      }

      // Still verifying on purpose: the state holds until the destination
      // replaces this page.
      await onSignedIn();
    } catch (err) {
      onError(
        err instanceof Error
          ? err.message
          : 'An unexpected error occurred. Please try again.',
      );
      setCode('');
      setBusy(false);
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
            disabled={verifying}
            className="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground disabled:pointer-events-none disabled:opacity-50"
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
          disabled={verifying}
          onResend={sendCode}
          autoFocus
          status={
            verifying ? (
              <div
                role="status"
                aria-live="polite"
                data-testid="phone-signin-verifying"
                className="flex h-11 w-full items-center justify-center gap-2 rounded-md bg-muted text-sm animate-in fade-in-0 duration-(--duration-fast) ease-(--ease-standard) motion-reduce:animate-none"
              >
                <LoaderCircleIcon
                  aria-hidden="true"
                  className="size-4 animate-spin text-muted-foreground motion-reduce:animate-none"
                />
                <span>
                  Signing you in
                  {sentTo ? (
                    <>
                      {' '}
                      as{' '}
                      <span className="font-medium whitespace-nowrap">
                        {sentTo}
                      </span>
                    </>
                  ) : null}
                </span>
              </div>
            ) : undefined
          }
        />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="space-y-1.5">
        <Label htmlFor="phone">Phone number</Label>
        <PhoneInput
          id="phone"
          value={phone}
          onChange={(e164, { valid }) => {
            setPhone(e164);
            setPhoneValid(valid);
            setShowPhoneError(false);
          }}
          showError={showPhoneError}
          disabled={requestCode.isPending}
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
