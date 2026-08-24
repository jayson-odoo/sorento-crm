import { apiFetch } from '@/lib/api';
import { extractApiError, buildDataGridParams } from '@/lib/api-client';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';
import type {
  LookupSet,
  LookupSetFormData,
  LookupOption,
  LookupOptionFormData,
  LookupBinding,
  LookupEligibility,
  LookupResolveResponse,
} from '../types/lookup.types';

const BASE = '/api/v1/master-data/lookup-sets';

export async function listLookupSets(p: DataGridApiFetchParams): Promise<DataGridApiResponse<LookupSet>> {
  const qs = buildDataGridParams(p);
  const r = await apiFetch(`${BASE}?${qs}`);
  if (!r.ok) throw new Error(await extractApiError(r, 'Failed to load lookup sets'));
  return r.json();
}

export async function getLookupSet(id: string): Promise<LookupSet> {
  const r = await apiFetch(`${BASE}/${id}`);
  if (!r.ok) throw new Error(await extractApiError(r, 'Failed to load lookup set'));
  return r.json();
}

export async function createLookupSet(data: LookupSetFormData): Promise<LookupSet> {
  const r = await apiFetch(BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!r.ok) throw new Error(await extractApiError(r, 'Failed to create lookup set'));
  return r.json();
}

export async function updateLookupSet(id: string, data: Partial<LookupSetFormData>): Promise<LookupSet> {
  const r = await apiFetch(`${BASE}/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!r.ok) throw new Error(await extractApiError(r, 'Failed to update lookup set'));
  return r.json();
}

export async function deleteLookupSet(id: string): Promise<void> {
  const r = await apiFetch(`${BASE}/${id}`, { method: 'DELETE' });
  if (!r.ok) throw new Error(await extractApiError(r, 'Failed to delete lookup set'));
}

// Options

export async function listOptions(setId: string): Promise<LookupOption[]> {
  const r = await apiFetch(`${BASE}/${setId}/options?page=1&limit=200`);
  if (!r.ok) throw new Error(await extractApiError(r, 'Failed to load options'));
  return (await r.json()).data;
}

export async function createOption(setId: string, data: LookupOptionFormData): Promise<LookupOption> {
  const r = await apiFetch(`${BASE}/${setId}/options`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!r.ok) throw new Error(await extractApiError(r, 'Failed to create option'));
  return r.json();
}

export async function updateOption(
  setId: string,
  optionId: string,
  data: Partial<LookupOptionFormData>,
): Promise<LookupOption> {
  const r = await apiFetch(`${BASE}/${setId}/options/${optionId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!r.ok) throw new Error(await extractApiError(r, 'Failed to update option'));
  return r.json();
}

export async function deleteOption(setId: string, optionId: string): Promise<void> {
  const r = await apiFetch(`${BASE}/${setId}/options/${optionId}`, { method: 'DELETE' });
  if (!r.ok) throw new Error(await extractApiError(r, 'Failed to delete option'));
}

// Bindings

export async function listBindings(setId: string): Promise<LookupBinding[]> {
  const r = await apiFetch(`${BASE}/${setId}/bindings`);
  if (!r.ok) throw new Error(await extractApiError(r, 'Failed to load bindings'));
  return r.json();
}

export async function addBinding(
  setId: string,
  table_name: string,
  column_name: string,
): Promise<LookupBinding> {
  const r = await apiFetch(`${BASE}/${setId}/bindings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ table_name, column_name }),
  });
  if (!r.ok) throw new Error(await extractApiError(r, 'Failed to add binding'));
  return r.json();
}

export async function removeBinding(setId: string, bindingId: string): Promise<void> {
  const r = await apiFetch(`${BASE}/${setId}/bindings/${bindingId}`, { method: 'DELETE' });
  if (!r.ok) throw new Error(await extractApiError(r, 'Failed to remove binding'));
}

/**
 * R2 - set (or clear) the default option a binding pre-selects on new forms.
 *
 * EXPECTED API CONTRACT (Phase 2 wiring target - NOT yet implemented):
 *   PATCH /api/v1/master-data/lookup-sets/{setId}/bindings/{bindingId}
 *     body:  { default_value: string | null }   // null clears the default
 *     200:   the updated LookupBinding (incl. default_value)
 *   `default_value`, when non-null, MUST be an existing option `value` in the set
 *   (validated app-side). The by-binding read (GET /api/v1/lookup/by-binding)
 *   echoes it so LookupBoundField can pre-select it on new forms.
 *
 * PHASE 1 (current): MOCKED - no network call; echoes the input back.
 */
export async function setBindingDefaultValue(
  setId: string,
  bindingId: string,
  default_value: string | null,
): Promise<{ id: string; default_value: string | null }> {
  await new Promise((resolve) => setTimeout(resolve, 200));
  return { id: bindingId, default_value };
}

// Eligibility

export async function listEligibility(available = false): Promise<LookupEligibility[]> {
  const r = await apiFetch(`/api/v1/master-data/lookup-eligibility${available ? '?available=true' : ''}`);
  if (!r.ok) throw new Error(await extractApiError(r, 'Failed to load eligibility'));
  return r.json();
}

// Resolve

export async function resolveLookup(
  set_key: string,
  raw: string,
  locale?: string,
): Promise<LookupResolveResponse> {
  const r = await apiFetch('/api/v1/lookup/resolve', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ set_key, raw, locale }),
  });
  if (!r.ok) throw new Error(await extractApiError(r, 'Failed to resolve'));
  return r.json();
}
