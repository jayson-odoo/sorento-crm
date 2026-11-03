import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

/** The hard-delete grace window when nothing says otherwise (D7: 10s). */
export const DEFAULT_DEFERRED_DELETE_SECONDS = 10;

/**
 * The hard-delete grace window an admin sets in System Settings > General
 * (`system_settings.deferred_delete_seconds`, the same column the server's deferred actions
 * read through `form_action_grace.record_action_window_seconds`).
 *
 * Read off the narrow `/settings/app-config` projection every signed-in user may read; the full
 * settings blob is gated on `user_management.settings.view`. A projection without the field (or
 * with a value out of range) answers the default.
 */
export async function getDeferredDeleteSeconds(): Promise<number> {
  const response = await apiFetch('/api/user-management/settings/app-config');
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load settings'));
  const data = await response.json();
  const seconds = data?.deferred_delete_seconds;
  return typeof seconds === 'number' && Number.isFinite(seconds) && seconds >= 1
    ? Math.round(seconds)
    : DEFAULT_DEFERRED_DELETE_SECONDS;
}
