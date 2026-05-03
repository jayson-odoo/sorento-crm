/** API client for the tickets module. Mirrors complaintService.ts shape. */

import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type {
  Ticket,
  TicketAssignInput,
  TicketCreateInput,
  TicketKanban,
  TicketListFilters,
  TicketListResponse,
  TicketResolutionUpdateInput,
  TicketResponseUpdateInput,
  TicketStatusChangeInput,
  TicketUpdateInput,
  TicketWatchersUpdateInput,
} from '../types/ticket.types';

const BASE = '/api/v1/tickets-management/tickets';

function buildQuery(filters: TicketListFilters & { page?: number; limit?: number }): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(filters)) {
    if (v !== undefined && v !== null && v !== '') {
      sp.set(k, String(v));
    }
  }
  return sp.toString();
}

async function jsonOrThrow<T>(res: Response, fallback: string): Promise<T> {
  if (!res.ok) {
    throw new Error(await extractApiError(res, fallback));
  }
  return res.json() as Promise<T>;
}

export async function getTickets(
  params: TicketListFilters & { page?: number; limit?: number } = {},
): Promise<TicketListResponse> {
  const qs = buildQuery({ page: 1, limit: 50, ...params });
  const res = await apiFetch(`${BASE}${qs ? `?${qs}` : ''}`);
  return jsonOrThrow<TicketListResponse>(res, 'Failed to load tickets');
}

export async function getTicketsKanban(
  filters: TicketListFilters = {},
): Promise<TicketKanban> {
  const qs = buildQuery(filters);
  const res = await apiFetch(`${BASE}/kanban${qs ? `?${qs}` : ''}`);
  return jsonOrThrow<TicketKanban>(res, 'Failed to load kanban');
}

export async function getTicket(id: string): Promise<Ticket> {
  const res = await apiFetch(`${BASE}/${id}`);
  return jsonOrThrow<Ticket>(res, 'Failed to load ticket');
}

export async function createTicket(data: TicketCreateInput): Promise<Ticket> {
  const res = await apiFetch(BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return jsonOrThrow<Ticket>(res, 'Failed to create ticket');
}

export async function updateTicket(id: string, data: TicketUpdateInput): Promise<Ticket> {
  const res = await apiFetch(`${BASE}/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return jsonOrThrow<Ticket>(res, 'Failed to update ticket');
}

export async function deleteTicket(id: string): Promise<void> {
  const res = await apiFetch(`${BASE}/${id}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to delete ticket'));
}

export async function bulkDeleteTickets(ids: string[]): Promise<void> {
  const res = await apiFetch(`${BASE}/bulk-delete`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids }),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to bulk-delete tickets'));
}

export async function changeTicketStatus(
  id: string,
  data: TicketStatusChangeInput,
): Promise<Ticket> {
  const res = await apiFetch(`${BASE}/${id}/status`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return jsonOrThrow<Ticket>(res, 'Failed to change ticket status');
}

export async function assignTicket(
  id: string,
  data: TicketAssignInput,
): Promise<Ticket> {
  const res = await apiFetch(`${BASE}/${id}/assign`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return jsonOrThrow<Ticket>(res, 'Failed to assign ticket');
}

export async function updateTicketResponse(
  id: string,
  data: TicketResponseUpdateInput,
): Promise<Ticket> {
  const res = await apiFetch(`${BASE}/${id}/response`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return jsonOrThrow<Ticket>(res, 'Failed to save response');
}

export async function updateTicketResolution(
  id: string,
  data: TicketResolutionUpdateInput,
): Promise<Ticket> {
  const res = await apiFetch(`${BASE}/${id}/resolution`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return jsonOrThrow<Ticket>(res, 'Failed to save resolution');
}

export async function addTicketWatchers(
  id: string,
  data: TicketWatchersUpdateInput,
): Promise<Ticket> {
  const res = await apiFetch(`${BASE}/${id}/watchers`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return jsonOrThrow<Ticket>(res, 'Failed to add watchers');
}

export async function removeTicketWatcher(id: string, userId: string): Promise<void> {
  const res = await apiFetch(`${BASE}/${id}/watchers/${userId}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to remove watcher'));
}

export async function linkTicketAttachment(
  ticketId: string,
  attachmentId: string,
): Promise<{ id: string; attachment_id: string }> {
  const sp = new URLSearchParams({ attachment_id: attachmentId });
  const res = await apiFetch(`${BASE}/${ticketId}/attachments?${sp.toString()}`, {
    method: 'POST',
  });
  return jsonOrThrow(res, 'Failed to link attachment');
}

export async function unlinkTicketAttachment(linkId: string): Promise<void> {
  const res = await apiFetch(
    `/api/v1/tickets-management/tickets/attachments/${linkId}`,
    { method: 'DELETE' },
  );
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to unlink attachment'));
}
