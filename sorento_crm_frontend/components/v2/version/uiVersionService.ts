import { apiFetch } from '@/lib/api';
import type { ThemeMode, UiVersion } from './context';

const ME = '/api/v1/user-management/users/me';

/** PUT the user's version choice; true on success. Never throws. */
export async function putUiVersion(next: UiVersion): Promise<boolean> {
  try {
    const res = await apiFetch(`${ME}/ui-version`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ui_version: next }),
    });
    return res.ok;
  } catch {
    return false;
  }
}

/** PUT the user's light/dark/system choice; true on success. Never throws. */
export async function putThemeMode(next: ThemeMode): Promise<boolean> {
  try {
    const res = await apiFetch(`${ME}/theme-mode`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ theme_mode: next }),
    });
    return res.ok;
  } catch {
    return false;
  }
}
