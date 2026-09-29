import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type {
  EmailTheme,
  EmailThemePreview,
  EmailThemeResponse,
  EmailThemeSampleCode,
} from '../types/emailTheme.types';

export async function getEmailTheme(): Promise<EmailThemeResponse> {
  const response = await apiFetch('/api/v1/system/email-theme');
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load email theme'));
  return response.json();
}

export async function saveEmailTheme(theme: EmailTheme): Promise<EmailThemeResponse> {
  const response = await apiFetch('/api/v1/system/email-theme', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(theme),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to save email theme'));
  return response.json();
}

export async function previewEmailTheme(
  theme: EmailTheme,
  code: EmailThemeSampleCode,
): Promise<EmailThemePreview> {
  const response = await apiFetch('/api/v1/system/email-theme/preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ theme, code }),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to preview email theme'));
  return response.json();
}
