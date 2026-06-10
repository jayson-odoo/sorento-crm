import { apiFetch } from '@/lib/api';
import type { ConversationSLATrackingDetail } from '@/app/(protected)/sla-management/conversation-sla-tracking/types/conversationSLATracking.types';

export type FormSLASourceType =
  | 'stock_inquiry'
  | 'purchase_request'
  | 'sponsorship_form'
  | 'complaint'
  | 'ticket';

export async function getFormSLATrackers(
  sourceEntityType: FormSLASourceType,
  sourceEntityId: string,
): Promise<ConversationSLATrackingDetail[]> {
  const sp = new URLSearchParams({
    source_entity_type: sourceEntityType,
    source_entity_id: sourceEntityId,
  });
  const r = await apiFetch(
    `/api/v1/sla-management/conversation-sla-tracking/by-source?${sp.toString()}`,
  );
  if (!r.ok) {
    throw new Error('Failed to load SLA trackers');
  }
  return r.json();
}

export interface FormSLAConfig {
  id: string;
  source_entity_type: FormSLASourceType;
  stage_code: string;
  policy_id: string;
  agent_code: string;
  team_set_code: string | null;
  start_event: string;
  respond_event: string | null;
  resolve_event: string | null;
  next_config_id: string | null;
  advance_on_event: string | null;
  is_active: boolean;
  notify_assignee?: boolean;
  policy_code?: string | null;
  policy_name?: string | null;
  next_stage_code?: string | null;
  created_at: string;
  updated_at: string;
}

export interface FormSLAConfigInput {
  source_entity_type: FormSLASourceType;
  stage_code: string;
  policy_id: string;
  agent_code: string;
  team_set_code?: string | null;
  start_event: string;
  respond_event?: string | null;
  resolve_event?: string | null;
  next_config_id?: string | null;
  advance_on_event?: string | null;
  is_active?: boolean;
  notify_assignee?: boolean;
}

export async function listFormSLAConfigs(filters: {
  source_entity_type?: FormSLASourceType;
  is_active?: boolean;
} = {}): Promise<FormSLAConfig[]> {
  const sp = new URLSearchParams();
  if (filters.source_entity_type) sp.set('source_entity_type', filters.source_entity_type);
  if (filters.is_active !== undefined) sp.set('is_active', String(filters.is_active));
  const qs = sp.toString();
  const r = await apiFetch(
    `/api/v1/sla-management/form-sla-config${qs ? `?${qs}` : ''}`,
  );
  if (!r.ok) {
    throw new Error('Failed to load form SLA configs');
  }
  return r.json();
}

export async function getFormSLAConfig(id: string): Promise<FormSLAConfig> {
  const r = await apiFetch(`/api/v1/sla-management/form-sla-config/${id}`);
  if (!r.ok) {
    throw new Error('Failed to load form SLA config');
  }
  return r.json();
}

async function _readError(r: Response): Promise<string> {
  try {
    const j = await r.json();
    const d = j.detail;
    if (typeof d === 'string') return d;
    if (Array.isArray(d)) return d.map((x: { msg?: string }) => x.msg).filter(Boolean).join(' ');
    if (d && typeof d === 'object' && 'message' in d) return String((d as { message?: string }).message);
    return j.message || 'Request failed';
  } catch {
    return 'Request failed';
  }
}

export async function createFormSLAConfig(input: FormSLAConfigInput): Promise<FormSLAConfig> {
  const r = await apiFetch(`/api/v1/sla-management/form-sla-config`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  });
  if (!r.ok) throw new Error(await _readError(r));
  return r.json();
}

export async function updateFormSLAConfig(
  id: string,
  input: Partial<FormSLAConfigInput>,
): Promise<FormSLAConfig> {
  const r = await apiFetch(`/api/v1/sla-management/form-sla-config/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  });
  if (!r.ok) throw new Error(await _readError(r));
  return r.json();
}

export async function deleteFormSLAConfig(id: string): Promise<void> {
  const r = await apiFetch(`/api/v1/sla-management/form-sla-config/${id}`, {
    method: 'DELETE',
  });
  if (!r.ok) throw new Error(await _readError(r));
}

/**
 * Allowed event names per form type. Source of truth is the backend service:
 * any event added here must also be emitted by the backend on the corresponding
 * state transition (see procurement_service.py / complaints_service.py).
 */
export const FORM_SLA_EVENT_OPTIONS: Record<FormSLASourceType, readonly string[]> = {
  stock_inquiry: [
    'submit',
    'project_sales_approve',
    'project_sales_reject',
    'purchasing_decide',
    'purchasing_respond',
  ],
  purchase_request: [
    'submit',
    'send_for_approval',
    'reject_submitted',
    'approved',
    'approval_rejected',
    'resolved',
  ],
  sponsorship_form: [
    'submit',
    'send_for_approval',
    'reject_submitted',
    'approved',
    'approval_rejected',
    'resolved',
  ],
  complaint: [
    'submit',
    'technical_team_response',
    'approved',
    'rejected',
    'resolved',
  ],
  ticket: [
    'submit',
    'assigned',
    'responded',
    'resolved',
  ],
};

export const FORM_SLA_TYPE_LABELS: Record<FormSLASourceType, string> = {
  stock_inquiry: 'Stock Inquiry',
  purchase_request: 'Purchase Request',
  sponsorship_form: 'Sponsorship Form',
  complaint: 'Complaint',
  ticket: 'Ticket',
};
