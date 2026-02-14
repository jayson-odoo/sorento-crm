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

export async function getDirectoryTree(): Promise<AttachmentDirectoryTreeNode[]> {
  const response = await apiFetch('/api/v1/resource-management/directories/tree');
  if (!response.ok) throw new Error('Failed to fetch directory tree');
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
