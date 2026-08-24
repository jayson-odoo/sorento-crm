/**
 * When each of the two adoption prompts is shown (AC-P8 to AC-P14).
 *
 * Kept apart from the component because this is the part that has to be right:
 * everything else is a bar with two buttons. Pure - the caller reads the
 * browser and passes the answers in.
 *
 * The once-per-device memory is localStorage, and every touch of it is guarded:
 * it throws outright in some contexts (private windows, blocked storage), and a
 * prompt that crashes the page is worse than one that shows twice.
 */

export const INSTALL_DISMISSED_KEY = 'sorento.pushPrompt.installDismissed';
export const ENABLE_DISMISSED_KEY = 'sorento.pushPrompt.enableDismissed';

/** `Notification.permission`, plus the case where the API is absent entirely. */
export type PushPermission = NotificationPermission | 'unsupported';

export type PushPromptEnv = {
  /** A phone or tablet. The install pitch is not made on desktop (AC-P14). */
  isMobile: boolean;
  /** Running from the home screen (`display-mode: standalone`). */
  isStandalone: boolean;
  permission: PushPermission;
  /** A push subscription exists for this device. */
  subscribed: boolean;
  installDismissed: boolean;
  enableDismissed: boolean;
};

/**
 * Install: a mobile browser, not already the installed app, not dismissed, and
 * not on a device that already receives notifications (AC-P13).
 *
 * A device whose permission is granted but whose subscription is gone turned
 * push off in My Account; the pitch here is the app on the home screen, which
 * is still worth making, so it still shows.
 */
export function shouldShowInstallPrompt(env: PushPromptEnv): boolean {
  if (!env.isMobile || env.isStandalone) return false;
  if (env.installDismissed) return false;
  if (env.permission === 'granted' && env.subscribed) return false;
  return true;
}

/**
 * Enable: only inside the installed app, only while the browser has not been
 * asked yet. `denied` and `granted` both mean the question is settled, so it
 * never re-asks (AC-P12, AC-P13); My Account stays the way to change your mind.
 */
export function shouldShowEnablePrompt(env: PushPromptEnv): boolean {
  if (!env.isStandalone) return false;
  if (env.enableDismissed) return false;
  return env.permission === 'default';
}

/** Phones and tablets, from the user agent. */
export function isMobileUserAgent(userAgent: string | undefined | null): boolean {
  if (!userAgent) return false;
  return /Android|iPhone|iPad|iPod|Mobile|Silk|Opera Mini|IEMobile/i.test(userAgent);
}

export function readDismissed(key: string): boolean {
  try {
    return window.localStorage.getItem(key) === '1';
  } catch {
    return false;
  }
}

export function markDismissed(key: string): void {
  try {
    window.localStorage.setItem(key, '1');
  } catch {
    // Storage unavailable. The cost is one repeated prompt, which is the right
    // failure for a preference this small.
  }
}
