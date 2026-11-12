/**
 * UI v2 phase 0, slice S3 (red first). UAC C-7.
 *
 * EXPORT CONTRACT:
 *   components/v2/theme/V2ThemeProvider.tsx : V2ThemeProvider({ theme, mode, children })
 *     theme: { preset: 'sorento-blue' | 'sorento-red' | 'teal' | 'graphite' | 'indigo'; custom_hex: string | null }
 *            (the company's system_settings.theme, handed in by the caller; the provider does no fetching)
 *     mode : 'light' | 'dark' | 'system'   (the user's theme_mode)
 *     The brand hex is custom_hex when set, else the preset's hex (lib/theme/presets). The effective mode is
 *     mode, or for 'system' the OS preference (window.matchMedia('(prefers-color-scheme: dark)')).
 *     It generates tokens with lib/theme/generate and writes them as CSS custom properties on
 *     document.documentElement.style: --primary, --primary-hover, --primary-foreground, --primary-soft, --ring.
 *     In dark it adds the `dark` class on <html>; in light it removes it. The variables are in place before the
 *     children's FIRST render (no flash of v1 colours): children may be withheld for one commit, never rendered
 *     early. On unmount it removes the five variables it set (v1 and next-themes are left as they were).
 *   Pinned values come from the reference engine: Sorento Blue light #246bdd, dark #68a1fe; custom #b44d2e
 *   (light) resolves to #b44d2e; Teal light #238279.
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render } from '@testing-library/react';

import { V2ThemeProvider } from './V2ThemeProvider';

const html = () => document.documentElement;
const v = (name: string) => html().style.getPropertyValue(name).trim().toLowerCase();

let prefersDark = false;

function Spy({ seen }: { seen: string[] }) {
  seen.push(html().style.getPropertyValue('--primary').trim().toLowerCase());
  return <p>child</p>;
}

const blue = { preset: 'sorento-blue' as const, custom_hex: null };

beforeEach(() => {
  prefersDark = false;
  window.matchMedia = vi.fn().mockImplementation((q: string) => ({
    matches: q.includes('dark') ? prefersDark : false,
    media: q,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    onchange: null,
    dispatchEvent: vi.fn(),
  })) as never;
  html().removeAttribute('style');
  html().classList.remove('dark');
});

afterEach(() => {
  cleanup();
  html().removeAttribute('style');
  html().classList.remove('dark');
});

describe('V2ThemeProvider', () => {
  it('sets the Sorento Blue light tokens on <html>', () => {
    render(
      <V2ThemeProvider theme={blue} mode="light">
        <p>x</p>
      </V2ThemeProvider>,
    );
    expect(v('--primary')).toBe('#246bdd');
    expect(v('--primary-foreground')).toBe('#ffffff');
    expect(v('--primary-hover')).toBe('#1156c0');
    expect(v('--primary-soft')).toBe('#f0f5fe');
    expect(v('--ring')).toMatch(/^#[0-9a-f]{6}$/);
    expect(html().classList.contains('dark')).toBe(false);
  });

  it('children never render before the variables are in place', () => {
    const seen: string[] = [];
    render(
      <V2ThemeProvider theme={blue} mode="light">
        <Spy seen={seen} />
      </V2ThemeProvider>,
    );
    expect(seen.length).toBeGreaterThan(0);
    expect(seen.every((s) => s === '#246bdd')).toBe(true);
  });

  it('dark mode adds the dark class and uses the dark primary', () => {
    render(
      <V2ThemeProvider theme={blue} mode="dark">
        <p>x</p>
      </V2ThemeProvider>,
    );
    expect(html().classList.contains('dark')).toBe(true);
    expect(v('--primary')).toBe('#68a1fe');
    expect(v('--primary-foreground')).toBe('#00215c');
  });

  it('system follows the OS preference', () => {
    prefersDark = true;
    render(
      <V2ThemeProvider theme={blue} mode="system">
        <p>x</p>
      </V2ThemeProvider>,
    );
    expect(html().classList.contains('dark')).toBe(true);
    expect(v('--primary')).toBe('#68a1fe');
  });

  it('system with a light OS stays light', () => {
    render(
      <V2ThemeProvider theme={blue} mode="system">
        <p>x</p>
      </V2ThemeProvider>,
    );
    expect(html().classList.contains('dark')).toBe(false);
    expect(v('--primary')).toBe('#246bdd');
  });

  it('a custom hex wins over the preset; a preset id picks its hex', () => {
    const { rerender } = render(
      <V2ThemeProvider theme={{ preset: 'sorento-blue', custom_hex: '#b44d2e' }} mode="light">
        <p>x</p>
      </V2ThemeProvider>,
    );
    expect(v('--primary')).toBe('#b44d2e');
    rerender(
      <V2ThemeProvider theme={{ preset: 'teal', custom_hex: null }} mode="light">
        <p>x</p>
      </V2ThemeProvider>,
    );
    expect(v('--primary')).toBe('#238279');
  });

  it('a mode change re-applies the tokens', () => {
    const { rerender } = render(
      <V2ThemeProvider theme={blue} mode="light">
        <p>x</p>
      </V2ThemeProvider>,
    );
    rerender(
      <V2ThemeProvider theme={blue} mode="dark">
        <p>x</p>
      </V2ThemeProvider>,
    );
    expect(v('--primary')).toBe('#68a1fe');
    expect(html().classList.contains('dark')).toBe(true);
  });

  it('unmount removes what it set and leaves unrelated styles alone', () => {
    html().style.setProperty('--unrelated', '1px');
    const { unmount } = render(
      <V2ThemeProvider theme={blue} mode="light">
        <p>x</p>
      </V2ThemeProvider>,
    );
    unmount();
    for (const n of ['--primary', '--primary-hover', '--primary-foreground', '--primary-soft', '--ring']) {
      expect(v(n)).toBe('');
    }
    expect(html().style.getPropertyValue('--unrelated')).toBe('1px');
  });
});
