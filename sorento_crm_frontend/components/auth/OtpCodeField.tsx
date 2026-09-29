'use client';

/**
 * Shared verification-code field: "Verification code" label, the 6-digit
 * input, and the outline resend button - lifted out of `PortalVerifyCard`
 * (PLAN-unified-identity-26sep.md S1, AC-25) so `/signin`'s phone step reuses
 * the exact same look instead of a second copy. Both `PortalVerifyCard` and
 * `/signin` import this one component.
 *
 * `onComplete` fires once per distinct 6-digit value, the same guard
 * `PortalVerifyCard` used to keep inline (`lastAutoVerifiedRef`): it does not
 * fire while `pending`/`disabled`, or before a code has been `sent`, but
 * retries once those clear for the same still-current value - matching the
 * portal card's original auto-verify behaviour exactly.
 */

import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

export interface OtpCodeFieldProps {
  value: string;
  onChange: (value: string) => void;
  /** Fired once per distinct 6-digit value, once not pending/disabled and a code has been sent. */
  onComplete: (code: string) => void;
  /** Seconds left before "Resend code" is enabled again; 0 = enabled now. */
  cooldown: number;
  /** Whether a code has been sent at least once - "Send code" vs "Resend code". */
  sent: boolean;
  pending: boolean;
  disabled?: boolean;
  onResend: () => void;
  id?: string;
  autoFocus?: boolean;
  /**
   * Shown in the resend button's place, at the same height, while set - the
   * caller's "working on it" line (`/signin` uses it for "Signing you in").
   * Leaving it unset keeps the resend button, which is what every other
   * caller wants.
   */
  status?: ReactNode;
}

export function OtpCodeField({
  value,
  onChange,
  onComplete,
  cooldown,
  sent,
  pending,
  disabled,
  onResend,
  id = 'code',
  autoFocus,
  status,
}: OtpCodeFieldProps) {
  const lastAutoVerifiedRef = useRef<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const wasDisabledRef = useRef(Boolean(disabled));

  // A disabled input drops focus, so when the caller unlocks the field again
  // (a wrong code) the cursor goes straight back into it: retyping needs no
  // extra tap.
  useEffect(() => {
    if (wasDisabledRef.current && !disabled) inputRef.current?.focus();
    wasDisabledRef.current = Boolean(disabled);
  }, [disabled]);

  useEffect(() => {
    const trimmed = value.trim();
    // A cleared box (the phone step clears it after an error) re-arms the
    // guard, so retyping the same code after a network blip submits again.
    if (trimmed === '') lastAutoVerifiedRef.current = null;
    if (trimmed.length !== 6) return;
    if (pending || disabled) return;
    if (!sent) return;
    if (lastAutoVerifiedRef.current === trimmed) return;
    lastAutoVerifiedRef.current = trimmed;
    onComplete(trimmed);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, pending, disabled, sent]);

  return (
    <div data-testid="otp-code-field" className="space-y-4">
      <div className="space-y-1.5">
        <Label htmlFor={id}>Verification code</Label>
        <Input
          variant="lg"
          ref={inputRef}
          id={id}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          inputMode="numeric"
          maxLength={6}
          placeholder="6-digit code"
          autoComplete="one-time-code"
          disabled={disabled}
          autoFocus={autoFocus}
          className="text-center tracking-[0.4em] text-lg font-medium"
        />
      </div>

      {status ?? (
        <Button
          type="button"
          variant="outline"
          onClick={onResend}
          disabled={pending || disabled || cooldown > 0}
          className="h-11 w-full"
        >
          {cooldown > 0
            ? `Resend in ${cooldown}s`
            : sent
              ? 'Resend code'
              : 'Send code'}
        </Button>
      )}
    </div>
  );
}

/** The 1s resend-cooldown ticker, shared by every caller of {@link OtpCodeField}. */
export function useResendCooldown(): [number, (seconds: number) => void] {
  const [cooldown, setCooldown] = useState(0);

  useEffect(() => {
    if (cooldown <= 0) return;
    const t = window.setTimeout(() => setCooldown((c) => c - 1), 1000);
    return () => window.clearTimeout(t);
  }, [cooldown]);

  return [cooldown, setCooldown];
}
