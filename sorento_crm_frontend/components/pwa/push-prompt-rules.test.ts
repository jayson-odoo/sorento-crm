/**
 * The decision logic behind the two adoption prompts (AC-P8 to AC-P14).
 *
 * This is the whole feature: a prompt that shows when it should not is a nag,
 * and one that never shows is why a single device has ever installed the app.
 * The rendering is a bar with two buttons; the rules are what is worth pinning.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  INSTALL_DISMISSED_KEY,
  ENABLE_DISMISSED_KEY,
  isMobileUserAgent,
  markDismissed,
  readDismissed,
  shouldShowEnablePrompt,
  shouldShowInstallPrompt,
  type PushPromptEnv,
} from './push-prompt-rules';

/** A signed-in phone that has never seen either prompt. */
const phone: PushPromptEnv = {
  isMobile: true,
  isStandalone: false,
  permission: 'default',
  subscribed: false,
  installDismissed: false,
  enableDismissed: false,
};

/** The same phone, opened from the home screen. */
const installedApp: PushPromptEnv = { ...phone, isStandalone: true };

describe('shouldShowInstallPrompt', () => {
  it('shows once on a mobile browser where the app is not installed (AC-P8)', () => {
    expect(shouldShowInstallPrompt(phone)).toBe(true);
  });

  it('stays hidden after it has been dismissed on this device (AC-P8)', () => {
    expect(shouldShowInstallPrompt({ ...phone, installDismissed: true })).toBe(false);
  });

  it('never shows on desktop - the pitch is a phone in a pocket (AC-P14)', () => {
    expect(shouldShowInstallPrompt({ ...phone, isMobile: false })).toBe(false);
  });

  it('does not ask again inside the installed app', () => {
    expect(shouldShowInstallPrompt(installedApp)).toBe(false);
  });

  it('stays hidden when notifications are already on (AC-P13)', () => {
    expect(
      shouldShowInstallPrompt({ ...phone, permission: 'granted', subscribed: true }),
    ).toBe(false);
  });

  it('still shows when permission was granted but the subscription is gone', () => {
    // The user turned push off in My Account. The install pitch is about the
    // app on the home screen, which is still worth making.
    expect(
      shouldShowInstallPrompt({ ...phone, permission: 'granted', subscribed: false }),
    ).toBe(true);
  });

  it('shows on a browser with no notification support at all - install is the fix on iOS', () => {
    expect(shouldShowInstallPrompt({ ...phone, permission: 'unsupported' })).toBe(true);
  });
});

describe('shouldShowEnablePrompt', () => {
  it('asks once inside the installed app while permission is still default (AC-P11)', () => {
    expect(shouldShowEnablePrompt(installedApp)).toBe(true);
  });

  it('does not ask again once declined on this device (AC-P12)', () => {
    expect(shouldShowEnablePrompt({ ...installedApp, enableDismissed: true })).toBe(false);
  });

  it('does not ask again once the browser permission itself was denied (AC-P12)', () => {
    expect(shouldShowEnablePrompt({ ...installedApp, permission: 'denied' })).toBe(false);
  });

  it('stays hidden when permission is already granted (AC-P13)', () => {
    expect(
      shouldShowEnablePrompt({ ...installedApp, permission: 'granted', subscribed: true }),
    ).toBe(false);
  });

  it('stays hidden in a plain browser tab - the app has to be installed first (AC-P11)', () => {
    expect(shouldShowEnablePrompt(phone)).toBe(false);
  });

  it('stays hidden where the browser has no notification support', () => {
    expect(shouldShowEnablePrompt({ ...installedApp, permission: 'unsupported' })).toBe(false);
  });
});

describe('the two prompts together', () => {
  const every = (): PushPromptEnv[] => {
    const out: PushPromptEnv[] = [];
    for (const isMobile of [true, false]) {
      for (const isStandalone of [true, false]) {
        for (const permission of ['default', 'granted', 'denied', 'unsupported'] as const) {
          for (const subscribed of [true, false]) {
            for (const installDismissed of [true, false]) {
              for (const enableDismissed of [true, false]) {
                out.push({
                  isMobile,
                  isStandalone,
                  permission,
                  subscribed,
                  installDismissed,
                  enableDismissed,
                });
              }
            }
          }
        }
      }
    }
    return out;
  };

  it('are never both on screen at once', () => {
    for (const env of every()) {
      expect(shouldShowInstallPrompt(env) && shouldShowEnablePrompt(env)).toBe(false);
    }
  });

  it('shows neither once notifications are on, whatever else is true (AC-P13)', () => {
    for (const env of every()) {
      if (env.permission !== 'granted' || !env.subscribed) continue;
      expect(shouldShowInstallPrompt(env)).toBe(false);
      expect(shouldShowEnablePrompt(env)).toBe(false);
    }
  });
});

describe('isMobileUserAgent', () => {
  it('recognises the phones the pitch is aimed at', () => {
    const mobiles = [
      'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1',
      'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36',
      'Mozilla/5.0 (iPad; CPU OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1',
    ];
    for (const ua of mobiles) expect(isMobileUserAgent(ua)).toBe(true);
  });

  it('does not treat a desktop browser as a phone (AC-P14)', () => {
    const desktops = [
      'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0',
      'Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0',
    ];
    for (const ua of desktops) expect(isMobileUserAgent(ua)).toBe(false);
  });

  it('is false rather than throwing on a missing user agent', () => {
    expect(isMobileUserAgent('')).toBe(false);
    expect(isMobileUserAgent(undefined)).toBe(false);
  });
});

describe('the once-per-device memory', () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.restoreAllMocks();
  });

  it('remembers a dismissal', () => {
    expect(readDismissed(INSTALL_DISMISSED_KEY)).toBe(false);
    markDismissed(INSTALL_DISMISSED_KEY);
    expect(readDismissed(INSTALL_DISMISSED_KEY)).toBe(true);
  });

  it('keeps the memory of each prompt separate', () => {
    markDismissed(ENABLE_DISMISSED_KEY);
    expect(readDismissed(ENABLE_DISMISSED_KEY)).toBe(true);
    expect(readDismissed(INSTALL_DISMISSED_KEY)).toBe(false);
  });

  it('reads as "not dismissed" when localStorage throws, rather than crashing the page', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('SecurityError: access denied');
    });
    expect(() => readDismissed(INSTALL_DISMISSED_KEY)).not.toThrow();
    expect(readDismissed(INSTALL_DISMISSED_KEY)).toBe(false);
  });

  it('swallows a write that throws - one repeated prompt beats a broken page', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('QuotaExceededError');
    });
    expect(() => markDismissed(ENABLE_DISMISSED_KEY)).not.toThrow();
  });
});
