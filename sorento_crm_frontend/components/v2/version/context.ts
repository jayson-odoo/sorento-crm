'use client';

import { createContext } from 'react';

export type UiVersion = 'v1' | 'v2';
export type ThemeMode = 'light' | 'dark' | 'system';

export interface UiVersionState {
  /** The effective version; 'v1' while loading or when /me failed. */
  uiVersion: UiVersion;
  uiV2Available: boolean;
  /** The user's light/dark/system choice (server-stored). */
  themeMode: ThemeMode;
  isLoading: boolean;
  setUiVersion(next: UiVersion): Promise<boolean>;
  setThemeMode(next: ThemeMode): Promise<boolean>;
}

export const UiVersionContext = createContext<UiVersionState>({
  uiVersion: 'v1',
  uiV2Available: false,
  themeMode: 'system',
  isLoading: false,
  setUiVersion: async () => false,
  setThemeMode: async () => false,
});
