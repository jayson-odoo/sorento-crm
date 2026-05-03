/** API client for the generic ActivitiesNotesPanel. Mirrors
 * /api/v1/activities/{entity_type}/{entity_id}/* on the backend. */

import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type {
  EntityRespondContact,
  InternalNote,
  PagedActivities,
  PagedMessages,
  PagedNotes,
} from './types';

const BASE = '/api/v1/activities';

function encodeKey(entityType: string, entityId: string): string {
  return `${encodeURIComponent(entityType)}/${encodeURIComponent(entityId)}`;
}

async function jsonOrThrow<T>(res: Response, fallback: string): Promise<T> {
  if (!res.ok) throw new Error(await extractApiError(res, fallback));
  return res.json() as Promise<T>;
}

export async function listActivities(
  entityType: string,
  entityId: string,
  params?: { limit?: number; before?: string },
): Promise<PagedActivities> {
  const sp = new URLSearchParams();
  if (params?.limit != null) sp.set('limit', String(params.limit));
  if (params?.before) sp.set('before', params.before);
  const qs = sp.toString();
  const res = await apiFetch(
    `${BASE}/${encodeKey(entityType, entityId)}/activities${qs ? `?${qs}` : ''}`,
  );
  return jsonOrThrow<PagedActivities>(res, 'Failed to load activities');
}

export async function postActivity(
  entityType: string,
  entityId: string,
  body: { body_html: string; body_text?: string | null; mentioned_user_ids?: string[]; attachment_ids?: string[] },
): Promise<unknown> {
  const res = await apiFetch(`${BASE}/${encodeKey(entityType, entityId)}/activities`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      mentioned_user_ids: [],
      attachment_ids: [],
      ...body,
    }),
  });
  return jsonOrThrow(res, 'Failed to post activity');
}

export async function listNotes(
  entityType: string,
  entityId: string,
  params?: { limit?: number; before?: string },
): Promise<PagedNotes> {
  const sp = new URLSearchParams();
  if (params?.limit != null) sp.set('limit', String(params.limit));
  if (params?.before) sp.set('before', params.before);
  const qs = sp.toString();
  const res = await apiFetch(
    `${BASE}/${encodeKey(entityType, entityId)}/notes${qs ? `?${qs}` : ''}`,
  );
  return jsonOrThrow<PagedNotes>(res, 'Failed to load notes');
}

export async function postNote(
  entityType: string,
  entityId: string,
  body: { body_html: string; body_text?: string | null },
): Promise<InternalNote> {
  const res = await apiFetch(`${BASE}/${encodeKey(entityType, entityId)}/notes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return jsonOrThrow<InternalNote>(res, 'Failed to post note');
}

export async function patchNote(
  noteId: string,
  body: { body_html?: string; body_text?: string | null },
): Promise<InternalNote> {
  const res = await apiFetch(`${BASE}/notes/${encodeURIComponent(noteId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return jsonOrThrow<InternalNote>(res, 'Failed to update note');
}

export async function deleteNote(noteId: string): Promise<void> {
  const res = await apiFetch(`${BASE}/notes/${encodeURIComponent(noteId)}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to delete note'));
}

export async function listEntityContacts(
  entityType: string,
  entityId: string,
): Promise<EntityRespondContact[]> {
  const res = await apiFetch(`${BASE}/${encodeKey(entityType, entityId)}/contacts`);
  return jsonOrThrow<EntityRespondContact[]>(res, 'Failed to load contacts');
}

export async function listMessages(
  entityType: string,
  entityId: string,
  params: { contact_id: string; cursor?: string },
): Promise<PagedMessages> {
  const sp = new URLSearchParams({ contact_id: params.contact_id });
  if (params.cursor) sp.set('cursor', params.cursor);
  const res = await apiFetch(
    `${BASE}/${encodeKey(entityType, entityId)}/messages?${sp.toString()}`,
  );
  return jsonOrThrow<PagedMessages>(res, 'Failed to load messages');
}

export async function sendMessage(
  entityType: string,
  entityId: string,
  body: { contact_id: string; body: string; attachment_ids?: string[] },
): Promise<unknown> {
  const res = await apiFetch(`${BASE}/${encodeKey(entityType, entityId)}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ attachment_ids: [], ...body }),
  });
  return jsonOrThrow(res, 'Failed to send message');
}

export async function markMentionSeen(
  entityType: string,
  entityId: string,
  eventId: string,
): Promise<unknown> {
  const res = await apiFetch(
    `${BASE}/${encodeKey(entityType, entityId)}/mentions/${encodeURIComponent(eventId)}/seen`,
    { method: 'POST' },
  );
  return jsonOrThrow(res, 'Failed to mark mention as seen');
}
