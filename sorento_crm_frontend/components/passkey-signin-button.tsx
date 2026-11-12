'use client';

/**
 * The round "Passkey" button on /signin (PASSKEY-LOGIN AC-40), and the Email field's passkey
 * autofill (AC-41) when `autofill` is set.
 *
 * Renders nothing unless the browser can do WebAuthn, the address is a secure context and the
 * backend says passkeys are on; the support check runs first, so an unsupported browser never
 * asks the backend. Status and the ceremony come from `hooks/usePasskeys` (AC-46). Forwards
 * its ref and extra props to the button, so the page can wrap it in a `TooltipTrigger asChild`.
 *
 * AC-48: the autofill request is cancelled (`WebAuthnAbortService.cancelCeremony()`) while the
 * page signs in another way (it passes `disabled`) and when the button unmounts (phone sign-in,
 * or the page goes away), and starts again when the page bumps `autofillRound` after a failed
 * attempt.
 */

import { forwardRef, useEffect, useState, type ButtonHTMLAttributes } from 'react';
import { KeyRound } from 'lucide-react';
import { browserSupportsWebAuthnAutofill, WebAuthnAbortService } from '@simplewebauthn/browser';
import { Button } from '@/components/ui/button';
import { usePasskeySignIn, usePasskeyStatusQuery } from '@/hooks/usePasskeys';
import { browserCanUsePasskeys } from '@/lib/passkey';

interface PasskeySignInButtonProps
  extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'onError'> {
  onSignedIn: () => void | Promise<void>;
  onError: (message: string) => void;
  disabled?: boolean;
  /** Also offer passkeys in the Email field's autofill, where the browser supports it. */
  autofill?: boolean;
  /** Bumped by the page after a failed sign-in another way: the autofill request starts again. */
  autofillRound?: number;
}

const PasskeySignInButton = forwardRef<HTMLButtonElement, PasskeySignInButtonProps>(
  function PasskeySignInButton(
    { onSignedIn, onError, disabled, autofill, autofillRound, onClick, ...rest },
    ref,
  ) {
    const [supported] = useState(browserCanUsePasskeys);
    const status = usePasskeyStatusQuery(supported);
    const enabled = supported && status.data?.enabled === true;
    const { busy, start } = usePasskeySignIn({ onSignedIn, onError });

    useEffect(() => {
      if (!enabled || !autofill || disabled) return;
      const controller = new AbortController();
      browserSupportsWebAuthnAutofill()
        .then((ok) => {
          if (ok && !controller.signal.aborted) void start({ autofill: true, signal: controller.signal });
        })
        .catch(() => undefined);
      return () => {
        controller.abort();
        WebAuthnAbortService.cancelCeremony();
      };
      // `start` reads its callbacks at call time; the request restarts only on these.
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [enabled, autofill, disabled, autofillRound]);

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
          void start();
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
