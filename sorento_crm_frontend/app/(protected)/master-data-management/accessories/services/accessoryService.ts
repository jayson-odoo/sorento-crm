/**
 * Accessories - feature service. Layering: UI -> hooks -> THIS -> lib/api-client.
 *
 * Contract (`documentation/plans/dealer-kit/PLAN-pricetag-accessories-06nov.md`, API),
 * all under `/api/v1/master-data`; read = master_data.products.view, write = .edit:
 *  GET    /accessories?page&limit&query -> { data, pagination }
 *  POST   /accessories {name, spec?} -> 201 (409 duplicate name)
 *  PATCH  /accessories/{id} {name?, spec?}
 *  DELETE /accessories/{id} -> 204 (409 while listed on products or combos)
 *  POST   /accessories/{id}/image (multipart `file`) -> {attachment_id, url}
 *  DELETE /accessories/{id}/image -> 204
 *  GET|PUT /products/{id}/accessories and /product-combos/{id}/accessories
 *    PUT {items: [{accessory_id} | {product_id}]} replaces the whole ordered list -> { data }
 *    entries are {kind: 'accessory'|'product', id, name, spec, image, code, list_price, ...}
 */
import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';
import type {
  Accessory,
  AccessoryEntry,
  AccessoryImage,
  AccessoryItemRef,
  AccessoryOwnerKind,
  AccessoryWrite,
} from '../types/accessory.types';

const BASE = '/api/v1/master-data/accessories';

export async function getAccessories(
  params: DataGridApiFetchParams,
): Promise<DataGridApiResponse<Accessory>> {
  const res = await apiFetch(`${BASE}?${buildDataGridParams(params).toString()}`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load accessories'));
  return res.json();
}

/** The picker's server search: one page of matches. */
export async function searchAccessories(query: string, limit = 50): Promise<Accessory[]> {
  const qs = buildDataGridParams({ pageIndex: 0, pageSize: limit, sorting: [], searchQuery: query });
  const res = await apiFetch(`${BASE}?${qs.toString()}`);
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load accessories'));
  const body = (await res.json()) as { data?: Accessory[] };
  return body.data ?? [];
}

export async function createAccessory(write: AccessoryWrite): Promise<Accessory> {
  const res = await apiFetch(BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(write),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to add the accessory'));
  return (await res.json()) as Accessory;
}

export async function updateAccessory(
  id: string,
  write: Partial<AccessoryWrite>,
): Promise<Accessory> {
  const res = await apiFetch(`${BASE}/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(write),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to save the accessory'));
  return (await res.json()) as Accessory;
}

export async function deleteAccessory(id: string): Promise<void> {
  const res = await apiFetch(`${BASE}/${encodeURIComponent(id)}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to delete the accessory'));
}

export async function uploadAccessoryImage(id: string, file: File): Promise<AccessoryImage> {
  const form = new FormData();
  form.append('file', file);
  const res = await apiFetch(`${BASE}/${encodeURIComponent(id)}/image`, {
    method: 'POST',
    body: form,
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to upload the picture'));
  return (await res.json()) as AccessoryImage;
}

export async function deleteAccessoryImage(id: string): Promise<void> {
  const res = await apiFetch(`${BASE}/${encodeURIComponent(id)}/image`, { method: 'DELETE' });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to remove the picture'));
}

function ownerPath(kind: AccessoryOwnerKind, id: string): string {
  const root = kind === 'product' ? 'products' : 'product-combos';
  return `/api/v1/master-data/${root}/${encodeURIComponent(id)}/accessories`;
}

export async function listOwnerAccessories(
  kind: AccessoryOwnerKind,
  id: string,
): Promise<AccessoryEntry[]> {
  const res = await apiFetch(ownerPath(kind, id));
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load the accessories'));
  const body = (await res.json()) as { data?: AccessoryEntry[] };
  return body.data ?? [];
}

export async function replaceOwnerAccessories(
  kind: AccessoryOwnerKind,
  id: string,
  items: AccessoryItemRef[],
): Promise<AccessoryEntry[]> {
  const res = await apiFetch(ownerPath(kind, id), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ items }),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Failed to save the accessories'));
  const body = (await res.json()) as { data?: AccessoryEntry[] };
  return body.data ?? [];
}
