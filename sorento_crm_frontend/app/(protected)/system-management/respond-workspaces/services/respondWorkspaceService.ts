import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

export interface RespondWorkspace {
  id: string;
  space_id: string;
  name: string | null;
  base_url: string | null;
  whatsapp_number: string | null;
  is_active: boolean;
  is_default: boolean;
  api_key_masked: string | null;
  created_at: string;
  updated_at: string;
}

export interface RespondWorkspaceSelectItem {
  id: string;
  space_id: string;
  name: string | null;
  is_default: boolean;
}

export interface RespondWorkspaceCreateBody {
  space_id: string;
  name?: string | null;
  base_url?: string | null;
  whatsapp_number?: string | null;
  is_active?: boolean;
  is_default?: boolean;
  api_key: string;
}

export interface RespondWorkspaceUpdateBody {
  space_id?: string;
  name?: string | null;
  base_url?: string | null;
  whatsapp_number?: string | null;
  is_active?: boolean;
  is_default?: boolean;
  api_key?: string | null;
}

const base = '/api/v1/system/respond-workspaces';

export async function listRespondWorkspaces(): Promise<RespondWorkspace[]> {
  const response = await apiFetch(base);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to fetch workspaces'));
  return response.json();
}

export async function listRespondWorkspaceSelect(): Promise<RespondWorkspaceSelectItem[]> {
  const response = await apiFetch(`${base}/select`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to fetch workspace select'));
  return response.json();
}

export async function createRespondWorkspace(
  body: RespondWorkspaceCreateBody,
): Promise<RespondWorkspace> {
  const response = await apiFetch(base, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to create workspace'));
  return response.json();
}

export async function updateRespondWorkspace(
  id: string,
  body: RespondWorkspaceUpdateBody,
): Promise<RespondWorkspace> {
  const response = await apiFetch(`${base}/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to update workspace'));
  return response.json();
}

export async function deleteRespondWorkspace(id: string): Promise<void> {
  const response = await apiFetch(`${base}/${id}`, { method: 'DELETE' });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to delete workspace'));
}

export async function setDefaultRespondWorkspace(id: string): Promise<RespondWorkspace> {
  const response = await apiFetch(`${base}/${id}/set-default`, { method: 'POST' });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to set default workspace'));
  return response.json();
}
