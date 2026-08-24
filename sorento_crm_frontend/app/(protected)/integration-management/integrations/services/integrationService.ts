import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type {
  Integration,
  IntegrationCreatePayload,
  IntegrationUpdatePayload,
  IssuedKey,
} from '../types/integration.types';

const BASE = '/api/v1/integrations/manage';

export async function getIntegrations(): Promise<Integration[]> {
  const response = await apiFetch(BASE);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load integrations'));
  }
  const body = await response.json();
  return body.data ?? [];
}

export async function getIntegration(id: string): Promise<Integration> {
  const response = await apiFetch(`${BASE}/${id}`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load integration'));
  }
  return response.json();
}

export async function createIntegration(
  payload: IntegrationCreatePayload,
): Promise<Integration> {
  const response = await apiFetch(BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to create integration'));
  }
  return response.json();
}

export async function updateIntegration(
  id: string,
  payload: IntegrationUpdatePayload,
): Promise<Integration> {
  const response = await apiFetch(`${BASE}/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to update integration'));
  }
  return response.json();
}

export async function deleteIntegration(id: string): Promise<void> {
  const response = await apiFetch(`${BASE}/${id}`, { method: 'DELETE' });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to delete integration'));
  }
}

/**
 * Mint a key. The plaintext in the response is the only copy that will ever
 * exist - it is not retrievable afterwards, only rotated. Show it to the user
 * immediately; never write it to storage, a URL, or a log.
 */
export async function issueKey(integrationId: string): Promise<IssuedKey> {
  const response = await apiFetch(`${BASE}/${integrationId}/keys`, { method: 'POST' });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to issue key'));
  }
  return response.json();
}

/**
 * Issue a replacement key and start the grace window on the current one.
 * `graceDays: 0` kills the old key immediately - correct for a leaked
 * credential, disruptive for a routine rotation.
 */
export async function rotateKey(
  integrationId: string,
  graceDays = 7,
): Promise<IssuedKey> {
  const response = await apiFetch(`${BASE}/${integrationId}/keys/rotate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ grace_days: graceDays }),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to rotate key'));
  }
  return response.json();
}

export async function revokeKey(integrationId: string, keyId: string): Promise<void> {
  const response = await apiFetch(`${BASE}/${integrationId}/keys/${keyId}/revoke`, {
    method: 'POST',
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to revoke key'));
  }
}
