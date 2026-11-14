'use client';

import { useQuery } from '@tanstack/react-query';
import { DEFAULT_COMPANY_THEME, getCompanyTheme } from './themeService';
import type { CompanyTheme } from './V2ThemeProvider';

/**
 * The company brand (`system_settings.theme`) from the narrow app-config projection every signed-in
 * user can read. Falls back to Sorento Blue while loading or when the endpoint is unreachable.
 */
export function useCompanyTheme(): CompanyTheme {
  const { data } = useQuery({
    queryKey: ['system-app-config', 'theme'],
    queryFn: getCompanyTheme,
    staleTime: Infinity,
    refetchOnReconnect: false,
  });
  return data ?? DEFAULT_COMPANY_THEME;
}
