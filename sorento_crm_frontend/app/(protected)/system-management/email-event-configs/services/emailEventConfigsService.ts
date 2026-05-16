import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type {
  EmailEventConfig,
  EmailEventConfigUpdate,
} from '../types/emailEventConfig.types';

export async function listEmailEventConfigs(): Promise<EmailEventConfig[]> {
  const response = await apiFetch('/api/v1/system/email-event-configs');
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load event configs'));
  return response.json();
}

export async function updateEmailEventConfig(
  event_key: string,
  payload: EmailEventConfigUpdate,
): Promise<EmailEventConfig> {
  const response = await apiFetch(`/api/v1/system/email-event-configs/${event_key}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to update event config'));
  return response.json();
}
