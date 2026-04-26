import { apiFetch } from '@/lib/api';

const CM = '/api/commercial-management';

export type ConversationScope = 'activity' | 'internal_note';

export type ConversationMessageAuthor = {
  id: string;
  name: string | null;
  email: string | null;
};

export type ConversationMessage = {
  id: string;
  scope: ConversationScope;
  is_system: boolean;
  body_html: string;
  author: ConversationMessageAuthor | null;
  created_at: string;
};

type ListParams = { scope: ConversationScope };

export async function listProjectConversationMessages(
  projectId: string,
  params: ListParams,
): Promise<ConversationMessage[]> {
  const sp = new URLSearchParams({ scope: params.scope });
  const res = await apiFetch(`${CM}/projects/${encodeURIComponent(projectId)}/conversation-messages?${sp}`);
  if (!res.ok) throw new Error('Failed to load messages');
  return res.json();
}

export async function postProjectConversationMessage(
  projectId: string,
  body: { scope: ConversationScope; body_html: string },
): Promise<ConversationMessage> {
  const res = await apiFetch(`${CM}/projects/${encodeURIComponent(projectId)}/conversation-messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error('Failed to send message');
  return res.json();
}

export async function listLeadConversationMessages(
  leadId: string,
  params: ListParams,
): Promise<ConversationMessage[]> {
  const sp = new URLSearchParams({ scope: params.scope });
  const res = await apiFetch(`${CM}/leads/${encodeURIComponent(leadId)}/conversation-messages?${sp}`);
  if (!res.ok) throw new Error('Failed to load messages');
  return res.json();
}

export async function postLeadConversationMessage(
  leadId: string,
  body: { scope: ConversationScope; body_html: string },
): Promise<ConversationMessage> {
  const res = await apiFetch(`${CM}/leads/${encodeURIComponent(leadId)}/conversation-messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error('Failed to send message');
  return res.json();
}

export async function listMasterQuotationConversationMessages(
  masterId: string,
  params: ListParams,
): Promise<ConversationMessage[]> {
  const sp = new URLSearchParams({ scope: params.scope });
  const res = await apiFetch(
    `${CM}/master-quotations/${encodeURIComponent(masterId)}/conversation-messages?${sp}`,
  );
  if (!res.ok) throw new Error('Failed to load messages');
  return res.json();
}

export async function postMasterQuotationConversationMessage(
  masterId: string,
  body: { scope: ConversationScope; body_html: string },
): Promise<ConversationMessage> {
  const res = await apiFetch(`${CM}/master-quotations/${encodeURIComponent(masterId)}/conversation-messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error('Failed to send message');
  return res.json();
}

export async function listProjectTaskConversationMessages(
  projectId: string,
  taskId: string,
  params: ListParams,
): Promise<ConversationMessage[]> {
  const sp = new URLSearchParams({ scope: params.scope });
  const res = await apiFetch(
    `${CM}/projects/${encodeURIComponent(projectId)}/tasks/${encodeURIComponent(taskId)}/conversation-messages?${sp}`,
  );
  if (!res.ok) throw new Error('Failed to load messages');
  return res.json();
}

export async function postProjectTaskConversationMessage(
  projectId: string,
  taskId: string,
  body: { scope: ConversationScope; body_html: string },
): Promise<ConversationMessage> {
  const res = await apiFetch(
    `${CM}/projects/${encodeURIComponent(projectId)}/tasks/${encodeURIComponent(taskId)}/conversation-messages`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
  );
  if (!res.ok) throw new Error('Failed to send message');
  return res.json();
}

export async function listMasterQuotationTaskConversationMessages(
  masterId: string,
  taskId: string,
  params: ListParams,
): Promise<ConversationMessage[]> {
  const sp = new URLSearchParams({ scope: params.scope });
  const res = await apiFetch(
    `${CM}/master-quotations/${encodeURIComponent(masterId)}/tasks/${encodeURIComponent(taskId)}/conversation-messages?${sp}`,
  );
  if (!res.ok) throw new Error('Failed to load messages');
  return res.json();
}

export async function postMasterQuotationTaskConversationMessage(
  masterId: string,
  taskId: string,
  body: { scope: ConversationScope; body_html: string },
): Promise<ConversationMessage> {
  const res = await apiFetch(
    `${CM}/master-quotations/${encodeURIComponent(masterId)}/tasks/${encodeURIComponent(taskId)}/conversation-messages`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
  );
  if (!res.ok) throw new Error('Failed to send message');
  return res.json();
}
