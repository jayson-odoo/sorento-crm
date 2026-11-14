import { apiFetch } from '@/lib/api';
import { apiError } from '@/lib/api-client';
import type { CompanyTheme } from './V2ThemeProvider';

const APP_CONFIG = '/api/user-management/settings/app-config';
const GENERAL = '/api/user-management/settings/general';

export const DEFAULT_COMPANY_THEME: CompanyTheme = { preset: 'sorento-blue', custom_hex: null };

/** The company brand from the app-config projection every signed-in user can read. */
export async function getCompanyTheme(): Promise<CompanyTheme> {
  const response = await apiFetch(APP_CONFIG);
  if (!response.ok) throw new Error('Failed to fetch settings');
  const body = await response.json();
  const theme = body?.theme;
  return theme && typeof theme.preset === 'string'
    ? { preset: theme.preset, custom_hex: theme.custom_hex ?? null }
    : DEFAULT_COMPANY_THEME;
}

/** Save the company brand (needs `user_management.settings.edit`); throws the API's message on failure. */
export async function saveCompanyTheme(theme: { preset: string; custom_hex: string | null }): Promise<void> {
  const response = await apiFetch(GENERAL, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ theme }),
  });
  if (!response.ok) throw await apiError(response, 'Could not save the brand colour');
}
