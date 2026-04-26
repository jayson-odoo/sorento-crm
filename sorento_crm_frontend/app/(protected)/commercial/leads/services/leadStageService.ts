import { apiFetch } from '@/lib/api';
import type { CommercialLeadStage } from '../types/lead.types';

const BASE = '/api/v1/commercial/lead-stages';

export type LeadStageCreatePayload = Pick<
  CommercialLeadStage,
  'stage_code' | 'stage_name' | 'sort_order' | 'is_terminal' | 'allows_conversion'
>;

export async function getLeadStages(): Promise<CommercialLeadStage[]> {
  const response = await apiFetch(BASE);
  if (!response.ok) throw new Error('Failed to fetch lead stages');
  return response.json();
}

export async function getLeadStageByCode(stageCode: string): Promise<CommercialLeadStage> {
  const response = await apiFetch(`${BASE}/by-code/${encodeURIComponent(stageCode)}`);
  if (!response.ok) throw new Error('Failed to load lead stage');
  return response.json();
}

export async function createLeadStage(data: LeadStageCreatePayload): Promise<CommercialLeadStage> {
  const response = await apiFetch(BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error((err as { detail?: string; message?: string }).detail || (err as { message?: string }).message || 'Failed to create stage');
  }
  return response.json();
}

export async function updateLeadStage(
  id: string,
  data: Partial<
    Pick<
      CommercialLeadStage,
      'stage_name' | 'sort_order' | 'is_terminal' | 'allows_conversion' | 'can_go_back' | 'is_active' | 'is_cancelled'
    >
  >,
): Promise<CommercialLeadStage> {
  const response = await apiFetch(`${BASE}/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to update stage');
  }
  return response.json();
}

export async function updateLeadStageByCode(
  stageCode: string,
  data: Partial<
    Pick<
      CommercialLeadStage,
      'stage_name' | 'sort_order' | 'is_terminal' | 'allows_conversion' | 'can_go_back' | 'is_active' | 'is_cancelled'
    >
  >,
): Promise<CommercialLeadStage> {
  const response = await apiFetch(`${BASE}/by-code/${encodeURIComponent(stageCode)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to update stage');
  }
  return response.json();
}

export async function deleteLeadStage(id: string): Promise<void> {
  const response = await apiFetch(`${BASE}/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to delete stage');
  }
}

export async function deleteLeadStageByCode(stageCode: string): Promise<void> {
  const response = await apiFetch(`${BASE}/by-code/${encodeURIComponent(stageCode)}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to delete stage');
  }
}
