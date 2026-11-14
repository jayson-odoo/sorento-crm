'use client';

import { useLayoutEffect, useRef, useState, useSyncExternalStore, type ReactNode } from 'react';
import { generateTheme } from '@/lib/theme/generate';
import { themeInputHex, type PresetId } from '@/lib/theme/presets';

export interface CompanyTheme {
  preset: PresetId | string;
  custom_hex: string | null;
}

export type ThemeModeChoice = 'light' | 'dark' | 'system';

export const THEME_VARIABLES = ['--primary', '--primary-hover', '--primary-foreground', '--primary-soft', '--ring'] as const;

const DARK_QUERY = '(prefers-color-scheme: dark)';

function subscribeOs(cb: () => void) {
  if (typeof window === 'undefined' || !window.matchMedia) return () => {};
  const mq = window.matchMedia(DARK_QUERY);
  mq.addEventListener?.('change', cb);
  return () => mq.removeEventListener?.('change', cb);
}

const osPrefersDark = () => typeof window !== 'undefined' && !!window.matchMedia?.(DARK_QUERY).matches;

/**
 * Applies the company brand and the user's mode to v2 (C-7): the generated tokens go on <html> as
 * CSS variables, and `dark` is toggled for dark mode. Children wait one commit so they never paint
 * with v1 colours. v1 never mounts this, so next-themes keeps working there unchanged.
 */
export function V2ThemeProvider({
  theme,
  mode,
  children,
}: {
  theme: CompanyTheme | null | undefined;
  mode: ThemeModeChoice;
  children: ReactNode;
}) {
  const prefersDark = useSyncExternalStore(subscribeOs, osPrefersDark, () => false);
  const effective = mode === 'system' ? (prefersDark ? 'dark' : 'light') : mode;
  const hex = themeInputHex(theme);
  const [applied, setApplied] = useState(false);
  // next-themes owns the `dark` class in v1; remember its state so a switch back to v1 restores it.
  const v1Theme = useRef<{ dark: boolean; light: boolean; scheme: string } | null>(null);

  useLayoutEffect(() => {
    const html = document.documentElement;
    if (v1Theme.current === null) {
      v1Theme.current = {
        dark: html.classList.contains('dark'),
        light: html.classList.contains('light'),
        scheme: html.style.colorScheme,
      };
    }
    const { tokens } = generateTheme(hex, effective);
    for (const name of THEME_VARIABLES) html.style.setProperty(name, tokens[name.slice(2) as keyof typeof tokens]);
    html.classList.toggle('dark', effective === 'dark');
    html.classList.toggle('light', effective === 'light');
    html.style.colorScheme = effective;
    setApplied(true);
  }, [hex, effective]);

  useLayoutEffect(
    () => () => {
      const html = document.documentElement;
      for (const name of THEME_VARIABLES) html.style.removeProperty(name);
      const v1 = v1Theme.current;
      if (v1) {
        html.classList.toggle('dark', v1.dark);
        html.classList.toggle('light', v1.light);
        html.style.colorScheme = v1.scheme;
      }
    },
    [],
  );

  return applied ? <>{children}</> : null;
}
