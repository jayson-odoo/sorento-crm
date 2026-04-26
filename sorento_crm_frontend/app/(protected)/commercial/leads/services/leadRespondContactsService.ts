import { apiFetch } from '@/lib/api';
import type { RespondConversationResponse } from '@/app/(protected)/procurement-management/stock-inquiries/services/stockInquiryService';
import type {
  LeadRespondContactRow,
  RespondContactBrief,
  RespondWorkspaceSelectItem,
} from '../types/lead.types';

export type LeadRespondConversationPayload = RespondConversationResponse & {
  inbox_url?: string | null;
  unavailable?: boolean;
};

export async function listRespondWorkspaceSelect(): Promise<RespondWorkspaceSelectItem[]> {
  const r = await apiFetch('/api/v1/commercial/respond-workspaces/select');
  if (!r.ok) throw new Error('Failed to load Respond workspaces');
  return r.json();
}

export async function searchRespondContacts(workspaceId: string, q?: string): Promise<RespondContactBrief[]> {
  const params = new URLSearchParams({ workspace_id: workspaceId });
  if (q?.trim()) params.set('q', q.trim());
  const r = await apiFetch(`/api/v1/commercial/respond-contacts/search?${params}`);
  if (!r.ok) throw new Error('Failed to search contacts');
  return r.json();
}

export async function listLeadRespondContacts(leadId: string): Promise<LeadRespondContactRow[]> {
  const r = await apiFetch(`/api/v1/commercial/leads/${encodeURIComponent(leadId)}/respond-contacts`);
  if (!r.ok) throw new Error('Failed to load lead contacts');
  return r.json();
}

export async function linkLeadRespondContact(
  leadId: string,
  body: {
    respond_contact_id: string;
    contact_role: 'main' | 'stakeholder';
    sort_order?: number;
  },
): Promise<LeadRespondContactRow> {
  const r = await apiFetch(`/api/v1/commercial/leads/${encodeURIComponent(leadId)}/respond-contacts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to link contact');
  }
  return r.json();
}

export async function linkLeadRespondContactFromPhone(
  leadId: string,
  body: {
    phone: string;
    name?: string | null;
    contact_role: 'main' | 'stakeholder';
    sort_order?: number;
  },
): Promise<LeadRespondContactRow> {
  const r = await apiFetch(`/api/v1/commercial/leads/${encodeURIComponent(leadId)}/respond-contacts/from-phone`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to add contact');
  }
  return r.json();
}

export async function updateLeadRespondContactLink(
  leadId: string,
  linkId: string,
  body: { contact_role?: 'main' | 'stakeholder'; sort_order?: number },
): Promise<LeadRespondContactRow> {
  const r = await apiFetch(
    `/api/v1/commercial/leads/${encodeURIComponent(leadId)}/respond-contacts/${encodeURIComponent(linkId)}`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
  );
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to update link');
  }
  return r.json();
}

export async function deleteLeadRespondContactLink(leadId: string, linkId: string): Promise<void> {
  const r = await apiFetch(
    `/api/v1/commercial/leads/${encodeURIComponent(leadId)}/respond-contacts/${encodeURIComponent(linkId)}`,
    { method: 'DELETE' },
  );
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Failed to remove link');
  }
}

export async function getLeadRespondConversation(
  leadId: string,
  respondContactId: string,
  params?: { limit?: number; cursor?: string },
): Promise<LeadRespondConversationPayload> {
  const sp = new URLSearchParams({ respond_contact_id: respondContactId });
  if (params?.limit != null) sp.set('limit', String(params.limit));
  if (params?.cursor) sp.set('cursor', params.cursor);
  const r = await apiFetch(
    `/api/v1/commercial/leads/${encodeURIComponent(leadId)}/respond-conversation?${sp}`,
  );
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Could not load messages');
  }
  return r.json();
}

export async function postLeadRespondConversationReply(
  leadId: string,
  respondContactId: string,
  message: string,
): Promise<void> {
  const sp = new URLSearchParams({ respond_contact_id: respondContactId });
  const r = await apiFetch(
    `/api/v1/commercial/leads/${encodeURIComponent(leadId)}/respond-conversation/reply?${sp}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message }),
    },
  );
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || 'Could not send');
  }
}
