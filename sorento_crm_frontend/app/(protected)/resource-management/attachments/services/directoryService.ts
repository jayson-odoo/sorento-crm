import { apiFetch } from '@/lib/api';

export interface AttachmentDirectory {
  id: string;
  name: string;
  parent_id: string | null;
  sort_order: number | null;
  created_at: string;
}

export interface AttachmentDirectoryTreeNode extends AttachmentDirectory {
  children: AttachmentDirectoryTreeNode[];
}

export async function getDirectoryTree(deleted = false): Promise<AttachmentDirectoryTreeNode[]> {
  const url = deleted
    ? '/api/v1/resource-management/directories/tree?deleted=true'
    : '/api/v1/resource-management/directories/tree';
  const response = await apiFetch(url);
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    const msg = err?.detail?.message ?? err?.detail ?? 'Failed to fetch directory tree';
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
  }
  return response.json();
}

export async function restoreDirectory(id: string): Promise<{ message: string; directories_restored: number; attachments_restored: number }> {
  const response = await apiFetch(`/api/v1/resource-management/directories/${id}/restore`, {
    method: 'POST',
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to restore directory');
  }
  return response.json();
}

export async function listDirectories(parentId?: string | null): Promise<AttachmentDirectory[]> {
  const params = new URLSearchParams();
  if (parentId != null && parentId !== '') params.set('parent_id', parentId);
  const response = await apiFetch(`/api/v1/resource-management/directories?${params.toString()}`);
  if (!response.ok) throw new Error('Failed to fetch directories');
  const data = await response.json();
  return Array.isArray(data) ? data : data.data ?? [];
}

export async function createDirectory(name: string, parentId?: string | null): Promise<AttachmentDirectory> {
  const response = await apiFetch('/api/v1/resource-management/directories', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, parent_id: parentId || null, sort_order: null }),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to create directory');
  }
  return response.json();
}

export async function updateDirectory(id: string, data: { name?: string; parent_id?: string | null; sort_order?: number | null }): Promise<AttachmentDirectory> {
  const response = await apiFetch(`/api/v1/resource-management/directories/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to update directory');
  }
  return response.json();
}

export async function deleteDirectory(id: string): Promise<void> {
  const response = await apiFetch(`/api/v1/resource-management/directories/${id}`, { method: 'DELETE' });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to delete directory');
  }
}

export async function permanentDeleteDirectory(id: string): Promise<{ message: string; directories_deleted: number; attachments_deleted: number }> {
  const response = await apiFetch(`/api/v1/resource-management/directories/${id}/permanent-delete`, {
    method: 'POST',
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to permanently delete directory');
  }
  return response.json();
}
