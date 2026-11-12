'use client';

/**
 * The round "Passkey" button on /signin (PASSKEY-LOGIN AC-40), and the Email field's passkey
 * autofill (AC-41) when `autofill` is set.
 *
 * Renders nothing unless the browser can do WebAuthn, the address is a secure context and the
 * backend says passkeys are on; the support check runs first, so an unsupported browser never
 * asks the backend. A cancelled browser prompt shows nothing; a refusal goes to `onError` as the
 * backend's own message. Forwards its ref and extra props to the button, so the page can wrap
 * it in a `TooltipTrigger asChild`.
 */

import { forwardRef, useEffect, useRef, useState, type ButtonHTMLAttributes } from 'react';
import { KeyRound } from 'lucide-react';
import { signIn } from 'next-auth/react';
import { browserSupportsWebAuthnAutofill, startAuthentication } from '@simplewebauthn/browser';
import { Button } from '@/components/ui/button';
import { browserCanUsePasskeys, isPasskeyPromptCancelled } from '@/lib/passkey';
import { fetchPasskeySignInOptions, fetchPasskeyStatus } from '@/services/passkeyService';

interface PasskeySignInButtonProps
  extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'onError'> {
  onSignedIn: () => void | Promise<void>;
  onError: (message: string) => void;
  disabled?: boolean;
  /** Also offer passkeys in the Email field's autofill, where the browser supports it. */
  autofill?: boolean;
}

const PasskeySignInButton = forwardRef<HTMLButtonElement, PasskeySignInButtonProps>(
  function PasskeySignInButton({ onSignedIn, onError, disabled, autofill, onClick, ...rest }, ref) {
    const [enabled, setEnabled] = useState(false);
    const [busy, setBusy] = useState(false);
    const mounted = useRef(true);
    // The open autofill request. Aborted when the page starts a sign-in some other way (it
    // passes `disabled`) or unmounts, so a late answer never signs anyone in behind its back.
    const autofillRequest = useRef<AbortController | null>(null);

    useEffect(() => {
      mounted.current = true;
      if (browserCanUsePasskeys()) {
        fetchPasskeyStatus()
          .then((status) => {
            if (mounted.current) setEnabled(Boolean(status?.enabled));
          })
          .catch(() => undefined);
      }
      return () => {
        mounted.current = false;
        autofillRequest.current?.abort();
      };
    }, []);

    useEffect(() => {
      if (disabled) autofillRequest.current?.abort();
    }, [disabled]);

    async function run(signal?: AbortSignal) {
      const live = () => mounted.current && !signal?.aborted;
      try {
        const { challenge_id, options } = await fetchPasskeySignInOptions();
        if (!live()) return;
        const credential = await startAuthentication({
          optionsJSON: options,
          useBrowserAutofill: Boolean(signal),
        });
        if (!live()) return;
        setBusy(true);
        const response = await signIn('passkey', {
          redirect: false,
          challengeId: challenge_id,
          credential: JSON.stringify(credential),
        });
        if (!live()) return;
        if (response?.error) {
          let message = response.error;
          try {
            message = JSON.parse(response.error).message || response.error;
          } catch {
            // not JSON: shown as it is
          }
          setBusy(false);
          onError(message);
          return;
        }
        // Busy stays on through the route change, like the password sign-in.
        await onSignedIn();
      } catch (err) {
        if (mounted.current) setBusy(false);
        if (!live() || isPasskeyPromptCancelled(err)) return;
        onError(err instanceof Error ? err.message : "That passkey didn't work. Sign in another way.");
      }
    }

    // AC-41: the conditional (autofill) request, started once passkeys are known to be on.
    useEffect(() => {
      if (!enabled || !autofill) return;
      const controller = new AbortController();
      autofillRequest.current = controller;
      browserSupportsWebAuthnAutofill()
        .then((supported) => {
          if (supported && !controller.signal.aborted) void run(controller.signal);
        })
        .catch(() => undefined);
      return () => controller.abort();
      // `run` reads its props at call time; the request is started once.
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [enabled, autofill]);

    if (!enabled) return null;

    return (
      <Button
        ref={ref}
        type="button"
        variant="outline"
        mode="icon"
        shape="circle"
        size="lg"
        aria-label="Passkey"
        {...rest}
        onClick={(e) => {
          onClick?.(e);
          // A button press replaces any open autofill request (the library aborts it).
          void run();
        }}
        disabled={disabled || busy}
        aria-busy={busy}
      >
        <KeyRound />
      </Button>
    );
  },
);

export default PasskeySignInButton;
