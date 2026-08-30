/**
 * What to tell someone whose "enable notifications" attempt failed.
 *
 * Two surfaces ask the same question (My Account and the adoption bar), so the
 * copy lives in one place. It is toast copy on purpose: the guidance is only
 * useful in the seconds after the failure, and the page itself carries no
 * standing explanation.
 */

import type { PushSubscribeFailure } from '@/services/pushService';

export interface PushFailureMessage {
  title: string;
  description?: string;
}

/** Brave exposes itself here, and nowhere in the user agent string. */
function isBraveBrowser(): boolean {
  if (typeof navigator === 'undefined') return false;
  return !!(navigator as Navigator & { brave?: unknown }).brave;
}

export function describePushFailure(
  reason: PushSubscribeFailure,
  options?: { brave?: boolean },
): PushFailureMessage {
  const brave = options?.brave ?? isBraveBrowser();
  switch (reason) {
    case 'push-service-blocked':
      return {
        title: 'Browser blocked the push service',
        description: brave
          ? 'Open brave://settings/privacy, turn on "Use Google services for push messaging", then try again.'
          : 'This browser could not reach its push service. A VPN, firewall or ad blocker can cause this. Turn those off for this site, then try again.',
      };
    case 'permission-denied':
      return {
        title: 'Notifications are blocked for this site',
        description: 'Allow notifications in your browser site settings, then try again.',
      };
    case 'unsupported':
      return {
        title: 'This browser does not support notifications',
        description: 'On iPhone or iPad, add the app to your home screen first (iOS 16.4+).',
      };
    default:
      return {
        title: 'Could not enable notifications',
        description: 'Something went wrong. Please try again.',
      };
  }
}
