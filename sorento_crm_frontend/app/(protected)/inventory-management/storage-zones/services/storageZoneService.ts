import { apiFetch } from '@/lib/api';
import type { StorageZone, StorageZoneFormData, StorageZoneTreeItem } from '../types/storageZone.types';

export async function getStorageZonesTree(warehouseId?: string): Promise<StorageZoneTreeItem[]> {
  const queryParams = new URLSearchParams();
  if (warehouseId) queryParams.set('warehouse_id', warehouseId);
  const response = await apiFetch(`/api/v1/inventory/storage-zones/tree?${queryParams.toString()}`);
  if (!response.ok) throw new Error('Failed to fetch storage zones');
  return response.json();
}

export async function getStorageZone(id: string): Promise<StorageZone> {
  const response = await apiFetch(`/api/v1/inventory/storage-zones/${id}`);
  if (!response.ok) throw new Error('Failed to fetch storage zone');
  return response.json();
}

export async function createStorageZone(data: StorageZoneFormData): Promise<StorageZone> {
  const response = await apiFetch('/api/v1/inventory/storage-zones', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to create storage zone' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function updateStorageZone(id: string, data: Partial<StorageZoneFormData>): Promise<StorageZone> {
  const response = await apiFetch(`/api/v1/inventory/storage-zones/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to update storage zone' }));
    throw new Error(error.message);
  }
  return response.json();
}

export async function deleteStorageZone(id: string): Promise<void> {
  const response = await apiFetch(`/api/v1/inventory/storage-zones/${id}`, { method: 'DELETE' });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to delete storage zone' }));
    throw new Error(error.message);
  }
}

export async function moveStorageZone(id: string, warehouseId: string, displayOrder: number): Promise<void> {
  const response = await apiFetch(`/api/v1/inventory/storage-zones/${id}/move`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ warehouse_id: warehouseId, display_order: displayOrder }),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to move storage zone' }));
    throw new Error(error.message);
  }
}
