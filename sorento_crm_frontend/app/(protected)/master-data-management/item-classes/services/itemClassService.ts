/**
 * Item classes - feature service.
 *
 * Layering: hooks (useItemClasses) -> THIS service -> lib/api -> backend
 * `/api/v1/master-data/item-classes`.
 *
 * -- BACKEND CONTRACT, LIVE (`PLAN-item-class-29oct.md`) ------------------------------------
 *
 *   GET    /item-classes/?page&limit&query&sort&dir
 *          -> DataGridApiResponse<ItemClass>; sort keys item_class_code | item_class_name |
 *          is_active | created_at. Requires `master_data.item_classes.view`.
 *   GET    /item-classes/select?query&brand_id -> ItemClassSelectItem[] (active only);
 *          `brand_id` keeps the classes some product of that brand carries.
 *   GET    /item-classes/{id}  -> ItemClass
 *   POST   /item-classes/      body ItemClassFormData -> ItemClass (409 duplicate code)
 *   PUT    /item-classes/{id}  body Partial<ItemClassFormData> -> ItemClass
 *   Delete goes through the deferred record-action registry key `item_class.delete`
 *   (entity_type `item_class`); 409 when a contact is limited to the class.
 */
import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';
import type {
  ItemClass,
  ItemClassFormData,
  ItemClassSelectItem,
} from '../types/item-class.types';

const BASE = '/api/v1/master-data/item-classes';

export async function getItemClasses(
  params: DataGridApiFetchParams,
): Promise<DataGridApiResponse<ItemClass>> {
  const queryParams = buildDataGridParams(params);
  const response = await apiFetch(`${BASE}/?${queryParams.toString()}`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to fetch item classes'));
  }
  return (await response.json()) as DataGridApiResponse<ItemClass>;
}

/** Active classes; with `brandId`, only those a product of that brand carries. */
export async function getItemClassSelect(brandId?: string): Promise<ItemClassSelectItem[]> {
  const qs = new URLSearchParams();
  if (brandId) qs.set('brand_id', brandId);
  const suffix = qs.toString();
  const response = await apiFetch(`${BASE}/select${suffix ? `?${suffix}` : ''}`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not load item classes.'));
  }
  return (await response.json()) as ItemClassSelectItem[];
}

export async function getItemClass(id: string): Promise<ItemClass> {
  const response = await apiFetch(`${BASE}/${id}`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to fetch item class'));
  }
  return (await response.json()) as ItemClass;
}

export async function createItemClass(data: ItemClassFormData): Promise<ItemClass> {
  const response = await apiFetch(`${BASE}/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to create item class'));
  }
  return (await response.json()) as ItemClass;
}

export async function updateItemClass(
  id: string,
  data: Partial<ItemClassFormData>,
): Promise<ItemClass> {
  const response = await apiFetch(`${BASE}/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to update item class'));
  }
  return (await response.json()) as ItemClass;
}
