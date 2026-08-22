import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

/**
 * Per-portal-type revision policy (UAC A2 / A6).
 *
 * Contract:
 *   GET /api/v1/forms-management/revision-configs
 *     -> { items: PortalRevisionConfig[] }  one row per portal submission type
 *   PUT /api/v1/forms-management/revision-configs/{source_entity_type}
 *     body: { is_enabled, max_revisions, allowed_statuses, restart_stage_code }
 *     -> the updated PortalRevisionConfig
 *
 * `max_revisions = null` inherits the global `portal_max_revisions`.
 * `restart_stage_code = null` restarts at the first stage of the type's SLA chain.
 * A missing row means the type is disabled: the backend policy fails closed.
 */
export interface PortalRevisionConfig {
  source_entity_type: string;
  is_enabled: boolean;
  /** null = inherit the global cap. */
  max_revisions: number | null;
  allowed_statuses: string[];
  /** null = the first stage of this type's form-SLA chain. */
  restart_stage_code: string | null;
}

export type PortalRevisionConfigInput = Omit<PortalRevisionConfig, 'source_entity_type'>;

export async function listPortalRevisionConfigs(): Promise<PortalRevisionConfig[]> {
  const response = await apiFetch('/api/v1/forms-management/revision-configs');
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load revision configs'));
  }
  const data = await response.json();
  return (data?.items ?? []) as PortalRevisionConfig[];
}

export async function updatePortalRevisionConfig(
  sourceEntityType: string,
  input: PortalRevisionConfigInput,
): Promise<PortalRevisionConfig> {
  const response = await apiFetch(
    `/api/v1/forms-management/revision-configs/${sourceEntityType}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    },
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to save revision config'));
  }
  return response.json();
}

/**
 * The two globals live on `system_settings` and save through the existing
 * general-settings setattr path. `apiFetch('/api/user-management/...')` maps
 * straight to FastAPI and bypasses any Next route.ts proxy, so no proxy is added.
 */
export interface PortalRevisionGlobals {
  portal_revisions_enabled: boolean;
  portal_max_revisions: number;
}

export async function savePortalRevisionGlobals(
  globals: PortalRevisionGlobals,
): Promise<void> {
  const response = await apiFetch('/api/user-management/settings/general', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(globals),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to save settings'));
  }
}
