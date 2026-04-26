import { apiFetch } from '@/lib/api';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';
import type {
  CommercialLead,
  CommercialLeadConvertPayload,
  CommercialLeadCreatePayload,
  CommercialLeadNote,
  CommercialLeadUpdatePayload,
  LeadRelatedResponse,
} from '../types/lead.types';

export async function getCommercialLeads(
  params: DataGridApiFetchParams & {
    customer_id?: string;
    owner_user_id?: string;
    lead_stage_id?: string;
    open_pipeline_only?: boolean;
    terminal_pipeline_only?: boolean;
    customer_active_only?: boolean;
    created_from?: string;
    created_to?: string;
  },
): Promise<DataGridApiResponse<CommercialLead>> {
  const {
    pageIndex,
    pageSize,
    sorting,
    searchQuery,
    customer_id,
    owner_user_id,
    lead_stage_id,
    open_pipeline_only,
    terminal_pipeline_only,
    customer_active_only,
    created_from,
    created_to,
  } = params;
  const sortField = sorting?.[0]?.id || '';
  const sortDirection = sorting?.[0]?.desc ? 'desc' : 'asc';
  const search = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(pageSize),
    ...(sortField ? { sort: sortField, dir: sortDirection } : {}),
    ...(searchQuery ? { query: searchQuery } : {}),
    ...(customer_id ? { customer_id } : {}),
    ...(owner_user_id ? { owner_user_id } : {}),
    ...(lead_stage_id ? { lead_stage_id } : {}),
    ...(open_pipeline_only ? { open_pipeline_only: 'true' } : {}),
    ...(terminal_pipeline_only ? { terminal_pipeline_only: 'true' } : {}),
    ...(customer_active_only ? { customer_active_only: 'true' } : {}),
    ...(created_from ? { created_from } : {}),
    ...(created_to ? { created_to } : {}),
  });
  const response = await apiFetch(`/api/v1/commercial/leads?${search.toString()}`);
  if (!response.ok) throw new Error('Failed to fetch leads');
  return response.json();
}

export async function getCommercialLead(id: string): Promise<CommercialLead> {
  const response = await apiFetch(`/api/v1/commercial/leads/${encodeURIComponent(id)}`);
  if (!response.ok) throw new Error('Failed to fetch lead');
  return response.json();
}

export async function getLeadRelated(leadId: string): Promise<LeadRelatedResponse> {
  const response = await apiFetch(`/api/v1/commercial/leads/${encodeURIComponent(leadId)}/related`);
  if (!response.ok) throw new Error('Failed to fetch lead related data');
  return response.json();
}

export async function duplicateCommercialLead(id: string): Promise<CommercialLead> {
  const response = await apiFetch(`/api/v1/commercial/leads/${encodeURIComponent(id)}/duplicate`, {
    method: 'POST',
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to duplicate lead');
  }
  return response.json();
}

export async function createCommercialLead(data: CommercialLeadCreatePayload): Promise<CommercialLead> {
  const response = await apiFetch('/api/v1/commercial/leads', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to create lead');
  }
  return response.json();
}

export async function updateCommercialLead(
  id: string,
  data: CommercialLeadUpdatePayload,
): Promise<CommercialLead> {
  const response = await apiFetch(`/api/v1/commercial/leads/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to update lead');
  }
  return response.json();
}

export async function deleteCommercialLead(id: string): Promise<void> {
  const response = await apiFetch(`/api/v1/commercial/leads/${encodeURIComponent(id)}`, { method: 'DELETE' });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to delete lead');
  }
}

export async function getLeadNotes(leadId: string): Promise<CommercialLeadNote[]> {
  const response = await apiFetch(`/api/v1/commercial/leads/${encodeURIComponent(leadId)}/notes`);
  if (!response.ok) throw new Error('Failed to fetch notes');
  return response.json();
}

export async function addLeadNote(leadId: string, body: string): Promise<CommercialLeadNote> {
  const response = await apiFetch(`/api/v1/commercial/leads/${encodeURIComponent(leadId)}/notes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ body }),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to add note');
  }
  return response.json();
}

export async function convertCommercialLead(
  leadId: string,
  data: CommercialLeadConvertPayload,
): Promise<{ lead_id: string; project_id: string; tender_id: string; tender_code: string }> {
  const response = await apiFetch(`/api/v1/commercial/leads/${encodeURIComponent(leadId)}/convert`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to convert lead');
  }
  return response.json();
}
