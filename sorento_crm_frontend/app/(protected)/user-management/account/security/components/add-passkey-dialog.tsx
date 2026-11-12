'use client';

import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { OtpCodeField, useResendCooldown } from '@/components/auth/OtpCodeField';
import { useAddPasskeyMutation, useSendPasskeyReauthCodeMutation } from '@/hooks/usePasskeys';
import type { PasskeyProof } from '@/services/passkeyService';

/**
 * "Confirm it's you" (PASSKEY-LOGIN AC-27 / AC-44): the password, or a code sent to the user's
 * own phone, before the browser's passkey prompt. A user without a password gets the code only.
 */
export function AddPasskeyDialog({
  open,
  onOpenChange,
  hasPassword,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  hasPassword: boolean;
}) {
  const [usePhone, setUsePhone] = useState(!hasPassword);
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cooldown, setCooldown] = useResendCooldown();
  const add = useAddPasskeyMutation();
  const sendCode = useSendPasskeyReauthCodeMutation();

  useEffect(() => {
    if (!open) return;
    setUsePhone(!hasPassword);
    setPassword('');
    setCode('');
    setSent(false);
    setError(null);
  }, [open, hasPassword]);

  const submit = async (proof: PasskeyProof) => {
    setError(null);
    try {
      await add.mutateAsync(proof);
      // Added, or the browser prompt was cancelled: either way the check is spent.
      onOpenChange(false);
    } catch (err) {
      // Shown under the field; the dialog stays open for another try.
      setError(err instanceof Error ? err.message : 'Could not add the passkey.');
      if ('phone_code' in proof) setCode('');
    }
  };

  const send = async () => {
    try {
      await sendCode.mutateAsync();
      setSent(true);
      setCooldown(60);
    } catch {
      // Shown by the hook.
    }
  };

  const canContinue = usePhone ? code.trim().length === 6 : password.length > 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Confirm it&apos;s you</DialogTitle>
        </DialogHeader>
        <form
          className="flex flex-col gap-3 py-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (canContinue && !add.isPending) {
              void submit(usePhone ? { phone_code: code.trim() } : { password });
            }
          }}
        >
          {usePhone ? (
            <OtpCodeField
              id="passkey-code"
              value={code}
              onChange={setCode}
              onComplete={(c) => void submit({ phone_code: c })}
              cooldown={cooldown}
              sent={sent}
              pending={add.isPending || sendCode.isPending}
              onResend={() => void send()}
            />
          ) : (
            <div className="flex flex-col gap-2">
              <Label htmlFor="passkey-password">Password</Label>
              <Input
                id="passkey-password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoFocus
              />
              <Button
                type="button"
                variant="link"
                size="sm"
                className="h-auto self-start p-0"
                onClick={() => {
                  setUsePhone(true);
                  setError(null);
                }}
              >
                Use a phone code instead
              </Button>
            </div>
          )}
          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={add.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={!canContinue || add.isPending}>
              {add.isPending ? 'Adding...' : 'Continue'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
