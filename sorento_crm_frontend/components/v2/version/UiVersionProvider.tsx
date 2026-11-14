'use client';

import { useCallback, useEffect, useMemo, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { useAccountProfileForHeader } from '@/hooks/useAccountProfileForHeader';
import { UiVersionContext, type ThemeMode, type UiVersion, type UiVersionState } from './context';
import { putThemeMode, putUiVersion } from './uiVersionService';

/**
 * Holds the UI version for the whole protected app (UAC B-7..B-9). It reads the version once,
 * from the existing /me profile query; a missing field or a failed /me means v1. While v2 is the
 * effective version, <html> carries `data-ui="v2"` so the v2 token block applies.
 */
export function UiVersionProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const { profile, queryKey, isLoading } = useAccountProfileForHeader();

  const uiVersion: UiVersion = profile?.ui_version === 'v2' ? 'v2' : 'v1';
  const uiV2Available = profile?.ui_v2_available === true;
  const themeMode: ThemeMode =
    profile?.theme_mode === 'light' || profile?.theme_mode === 'dark' ? profile.theme_mode : 'system';

  useEffect(() => {
    const html = document.documentElement;
    if (uiVersion === 'v2') html.setAttribute('data-ui', 'v2');
    else html.removeAttribute('data-ui');
  }, [uiVersion]);

  useEffect(() => () => document.documentElement.removeAttribute('data-ui'), []);

  const keyString = JSON.stringify(queryKey);
  const patchProfile = useCallback(
    (patch: Record<string, unknown>) => {
      queryClient.setQueryData(JSON.parse(keyString), (old: Record<string, unknown> | null | undefined) =>
        old ? { ...old, ...patch } : old,
      );
    },
    [queryClient, keyString],
  );

  const setUiVersion = useCallback(
    async (next: UiVersion) => {
      const ok = await putUiVersion(next);
      if (!ok) {
        toast.error('We could not switch the version. Please try again.');
        return false;
      }
      // Same URL, other version: the shell re-renders from the cache, no navigation.
      patchProfile({ ui_version: next, ui_version_stored: next });
      return true;
    },
    [patchProfile],
  );

  const setThemeMode = useCallback(
    async (next: ThemeMode) => {
      const ok = await putThemeMode(next);
      if (!ok) {
        toast.error('We could not save the appearance. Please try again.');
        return false;
      }
      patchProfile({ theme_mode: next });
      return true;
    },
    [patchProfile],
  );

  const value = useMemo<UiVersionState>(
    () => ({ uiVersion, uiV2Available, themeMode, isLoading, setUiVersion, setThemeMode }),
    [uiVersion, uiV2Available, themeMode, isLoading, setUiVersion, setThemeMode],
  );

  return <UiVersionContext.Provider value={value}>{children}</UiVersionContext.Provider>;
}
