'use client';

import { useLayoutEffect, useState, useSyncExternalStore, type ReactNode } from 'react';
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

  useLayoutEffect(() => {
    const html = document.documentElement;
    const { tokens } = generateTheme(hex, effective);
    for (const name of THEME_VARIABLES) html.style.setProperty(name, tokens[name.slice(2) as keyof typeof tokens]);
    html.classList.toggle('dark', effective === 'dark');
    setApplied(true);
  }, [hex, effective]);

  useLayoutEffect(
    () => () => {
      const html = document.documentElement;
      for (const name of THEME_VARIABLES) html.style.removeProperty(name);
    },
    [],
  );

  return applied ? <>{children}</> : null;
}
