'use client';

/**
 * The two adoption prompts (AC-P8 to AC-P14): install the app, then turn
 * notifications on inside it. Each is shown at most once per device and is
 * dismissible; the rules for which one (if either) is on screen live in
 * `push-prompt-rules.ts`.
 *
 * There is no new preference and no new endpoint here - the browser
 * subscription IS the opt-in (TCK-33), so "enable" is just `subscribeToPush()`
 * moved to where the user already is instead of behind My Account.
 *
 * Rendered in flow at the top of the page body, so neither bar can ever cover
 * the primary action of the page beneath it (AC-P16).
 */

import { useEffect, useRef, useState } from 'react';
import { BellRing, Smartphone, X } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Container } from '@/components/common/container';
import { getPushState, subscribeToPush } from '@/services/pushService';
import { describePushFailure } from '@/lib/pushFailureMessage';

import {
  ENABLE_DISMISSED_KEY,
  INSTALL_DISMISSED_KEY,
  isMobileUserAgent,
  markDismissed,
  readDismissed,
  shouldShowEnablePrompt,
  shouldShowInstallPrompt,
  type PushPermission,
  type PushPromptEnv,
} from './push-prompt-rules';

/** Chrome/Edge only. Not in lib.dom, so it is declared where it is used. */
type BeforeInstallPromptEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
};

function readStandalone(): boolean {
  try {
    if (window.matchMedia?.('(display-mode: standalone)').matches) return true;
  } catch {
    // matchMedia unavailable
  }
  // iOS Safari predates display-mode and reports it here instead.
  return (window.navigator as Navigator & { standalone?: boolean }).standalone === true;
}

function readPermission(): PushPermission {
  return typeof Notification === 'undefined' ? 'unsupported' : Notification.permission;
}

export default function PushPrompts() {
  const [env, setEnv] = useState<PushPromptEnv | null>(null);
  const [isIOS, setIsIOS] = useState(false);
  const [showSteps, setShowSteps] = useState(false);
  const [busy, setBusy] = useState(false);
  const deferredInstall = useRef<BeforeInstallPromptEvent | null>(null);

  useEffect(() => {
    let alive = true;

    const onBeforeInstallPrompt = (event: Event) => {
      // Keep the browser's own banner off screen and fire it from our button.
      event.preventDefault();
      deferredInstall.current = event as BeforeInstallPromptEvent;
    };
    window.addEventListener('beforeinstallprompt', onBeforeInstallPrompt);

    const userAgent = window.navigator.userAgent;
    setIsIOS(/iPhone|iPad|iPod/i.test(userAgent));

    // getPushState settles immediately where push is unsupported, so this does
    // not delay the prompt on the browsers that need it most. Waiting for it
    // stops the install bar flashing on a device that is already subscribed.
    void getPushState().then((subscribed) => {
      if (!alive) return;
      setEnv({
        isMobile: isMobileUserAgent(userAgent),
        isStandalone: readStandalone(),
        permission: readPermission(),
        subscribed,
        installDismissed: readDismissed(INSTALL_DISMISSED_KEY),
        enableDismissed: readDismissed(ENABLE_DISMISSED_KEY),
      });
    });

    return () => {
      alive = false;
      window.removeEventListener('beforeinstallprompt', onBeforeInstallPrompt);
    };
  }, []);

  if (!env) return null;

  const showEnable = shouldShowEnablePrompt(env);
  const showInstall = shouldShowInstallPrompt(env);
  if (!showEnable && !showInstall) return null;

  const dismissInstall = () => {
    markDismissed(INSTALL_DISMISSED_KEY);
    setEnv((prev) => (prev ? { ...prev, installDismissed: true } : prev));
  };

  const dismissEnable = () => {
    markDismissed(ENABLE_DISMISSED_KEY);
    setEnv((prev) => (prev ? { ...prev, enableDismissed: true } : prev));
  };

  const onInstall = async () => {
    const deferred = deferredInstall.current;
    if (!deferred) {
      // iOS Safari, and any browser that never offered the event: there is no
      // programmatic install, so show the steps it does support (AC-P10).
      setShowSteps(true);
      return;
    }
    deferredInstall.current = null;
    setBusy(true);
    try {
      await deferred.prompt();
      await deferred.userChoice;
    } catch {
      // The browser declined to show it (already consumed / not eligible).
    } finally {
      setBusy(false);
    }
    // Asked once, whatever the answer was.
    dismissInstall();
  };

  const onEnable = async () => {
    setBusy(true);
    try {
      const result = await subscribeToPush();
      if (result.ok) {
        setEnv((prev) => (prev ? { ...prev, permission: 'granted', subscribed: true } : prev));
        toast.success('Notifications enabled');
      } else {
        // Declined, blocked, or the subscription could not be stored. Either way
        // the question has been asked; My Account is the way to change your mind.
        // The toast names what went wrong, so a fixable block (Brave's push
        // service being off) is not read as "this app is broken".
        dismissEnable();
        const { title, description } = describePushFailure(result.reason);
        toast.error(title, description ? { description } : undefined);
      }
    } finally {
      setBusy(false);
    }
  };

  const barClass =
    'mb-5 rounded-lg border border-primary/30 bg-primary/5 px-3 py-2.5 text-sm';
  const rowClass = 'flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between';

  if (showEnable) {
    return (
      <Container>
        <div className={barClass} role="region" aria-label="Enable notifications" data-testid="push-enable-prompt">
          <div className={rowClass}>
            <div className="flex min-w-0 items-start gap-2">
              <BellRing className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden />
              <p className="min-w-0 text-foreground/80">
                <span className="font-medium text-foreground">Turn on notifications</span>{' '}
                <span className="block sm:inline">Get alerts on this device even when the app is closed.</span>
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-2 self-end sm:self-auto">
              <Button size="sm" onClick={onEnable} disabled={busy} data-testid="push-enable-accept">
                Turn on
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={dismissEnable}
                disabled={busy}
                data-testid="push-enable-dismiss"
              >
                Not now
              </Button>
            </div>
          </div>
        </div>
      </Container>
    );
  }

  return (
    <Container>
      <div className={barClass} role="region" aria-label="Install Sorento" data-testid="push-install-prompt">
        <div className={rowClass}>
          <div className="flex min-w-0 items-start gap-2">
            <Smartphone className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden />
            <p className="min-w-0 text-foreground/80">
              <span className="font-medium text-foreground">Install Sorento on your phone</span>{' '}
              <span className="block sm:inline">Get SLA alerts even when the app is closed.</span>
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-2 self-end sm:self-auto">
            <Button size="sm" onClick={onInstall} disabled={busy} data-testid="push-install-accept">
              Install
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={dismissInstall}
              disabled={busy}
              className="size-8 p-0"
              aria-label="Dismiss install prompt"
              data-testid="push-install-dismiss"
            >
              <X className="size-4" />
            </Button>
          </div>
        </div>
        {showSteps && (
          <ol
            className="mt-2 list-decimal space-y-1 pl-10 text-xs text-muted-foreground"
            data-testid="push-install-steps"
          >
            {isIOS ? (
              <>
                <li>Tap the Share button in Safari.</li>
                <li>Choose Add to Home Screen.</li>
              </>
            ) : (
              <>
                <li>Open your browser menu.</li>
                <li>Choose Add to Home screen.</li>
              </>
            )}
          </ol>
        )}
      </div>
    </Container>
  );
}
