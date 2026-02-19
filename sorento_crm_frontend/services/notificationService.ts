import { apiFetch } from '@/lib/api';

export interface NotificationItem {
  id: string;
  user_id: string;
  type: string;
  title: string;
  body: string | null;
  data: Record<string, unknown> | null;
  read_at: string | null;
  archived_at: string | null;
  resolved_at: string | null;
  created_at: string;
  source_entity_type: string | null;
  source_entity_id: string | null;
  event_type: string | null;
}

export interface NotificationsListResponse {
  data: NotificationItem[];
  pagination: { total: number; page: number; limit: number };
  empty: boolean;
}

export interface UnreadCountResponse {
  count: number;
}

const base = '/api/v1/notifications';

export async function listNotifications(params: {
  tab?: 'all' | 'inbox' | 'archived';
  status?: 'read' | 'unread';
  type?: string;
  page?: number;
  limit?: number;
}): Promise<NotificationsListResponse> {
  const search = new URLSearchParams();
  if (params.tab) search.set('tab', params.tab);
  if (params.status) search.set('status', params.status);
  if (params.type) search.set('type', params.type);
  search.set('page', String(params.page ?? 1));
  search.set('limit', String(params.limit ?? 50));
  const res = await apiFetch(`${base}?${search.toString()}`);
  if (!res.ok) throw new Error('Failed to fetch notifications');
  return res.json();
}

export async function getUnreadCount(includeArchived = false): Promise<number> {
  const res = await apiFetch(`${base}/unread-count?include_archived=${includeArchived}`);
  if (!res.ok) throw new Error('Failed to fetch unread count');
  const data: UnreadCountResponse = await res.json();
  return data.count;
}

export async function markRead(notificationId: string): Promise<NotificationItem> {
  const res = await apiFetch(`${base}/${notificationId}/read`, { method: 'PATCH' });
  if (!res.ok) throw new Error('Failed to mark as read');
  return res.json();
}

export async function markUnread(notificationId: string): Promise<NotificationItem> {
  const res = await apiFetch(`${base}/${notificationId}/unread`, { method: 'PATCH' });
  if (!res.ok) throw new Error('Failed to mark as unread');
  return res.json();
}

export async function markAllRead(archived?: boolean): Promise<{ count: number }> {
  const url = archived !== undefined ? `${base}/mark-all-read?archived=${archived}` : `${base}/mark-all-read`;
  const res = await apiFetch(url, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to mark all as read');
  return res.json();
}

export async function archive(notificationId: string): Promise<NotificationItem> {
  const res = await apiFetch(`${base}/${notificationId}/archive`, { method: 'PATCH' });
  if (!res.ok) throw new Error('Failed to archive');
  return res.json();
}

export async function archiveAll(): Promise<{ count: number }> {
  const res = await apiFetch(`${base}/archive-all`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  });
  if (!res.ok) throw new Error('Failed to clear all');
  return res.json();
}

export async function resolve(notificationId: string): Promise<NotificationItem> {
  const res = await apiFetch(`${base}/${notificationId}/resolve`, { method: 'PATCH' });
  if (!res.ok) throw new Error('Failed to resolve');
  return res.json();
}
