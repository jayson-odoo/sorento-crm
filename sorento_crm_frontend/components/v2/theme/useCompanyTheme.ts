'use client';

import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api';
import type { CompanyTheme } from './V2ThemeProvider';

const DEFAULT_THEME: CompanyTheme = { preset: 'sorento-blue', custom_hex: null };

/**
 * The company brand (`system_settings.theme`) from the narrow app-config projection every signed-in
 * user can read. Falls back to Sorento Blue while loading or when the endpoint is unreachable.
 */
export function useCompanyTheme(): CompanyTheme {
  const { data } = useQuery({
    queryKey: ['system-app-config', 'theme'],
    queryFn: async (): Promise<CompanyTheme> => {
      const response = await apiFetch('/api/user-management/settings/app-config');
      if (!response.ok) throw new Error('Failed to fetch settings');
      const body = await response.json();
      const theme = body?.theme;
      return theme && typeof theme.preset === 'string'
        ? { preset: theme.preset, custom_hex: theme.custom_hex ?? null }
        : DEFAULT_THEME;
    },
    staleTime: Infinity,
    refetchOnReconnect: false,
  });
  return data ?? DEFAULT_THEME;
}
