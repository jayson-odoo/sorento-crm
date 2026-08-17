/**
 * Units of measure - feature service.
 *
 * Layering: hooks (useUOM) -> THIS service -> lib/api -> backend
 * `/api/v1/master-data/units-of-measure`.
 *
 * -- PHASE-2 BACKEND CONTRACT (slice S2-BE-1) --------------------------------
 * The unit gains ONE field, `decimal_places`, and it appears on every shape the
 * unit already travels in (AC-F12):
 *
 *   GET    /units-of-measure           list rows   += decimal_places: number
 *   GET    /units-of-measure/{id}      detail      += decimal_places: number
 *   GET    /units-of-measure/select    select rows += decimal_places: number
 *   POST   /units-of-measure           body        += decimal_places?: number
 *   PUT    /units-of-measure/{id}      body        += decimal_places?: number
 *
 * Rules the routes enforce, and the reasons they are not negotiable:
 *
 *   - **`0..4`, validated on every write.** Outside that range is rejected. It is
 *     canonical UOM divisibility - `EA` is 0 and refuses `2.5`, `kg` at 3 accepts
 *     it - not SCM arithmetic precision, and it is never inferred from
 *     `conversion_factor`.
 *   - **Omitted on CREATE resolves to `0`**, the same fallback a missing rollout
 *     value takes. **Omitted on EDIT preserves the stored value**, so a partial
 *     update cannot silently reset a measure unit to whole numbers.
 *   - **The backfill classifies by NAME, never by code.** Count names get 0;
 *     measure names get the greatest fractional scale actually observed in the
 *     transaction columns, capped at 4; every unknown name gets 0. A unit coded
 *     `EA` but named `Kilogram` is therefore a measure unit, and no historical
 *     quantity is rewritten.
 *   - **SCM freezes it per run.** Each summary row copies the product's value as
 *     `uom_decimal_places` at calculation, and validation and allocation read that
 *     snapshot, so editing a unit here never changes a run already calculated.
 *
 * Phase 1: `USE_UOM_DECIMAL_PLACES_MOCKS` (in `lib/uomDecimalPlacesMockStore.ts`)
 * overlays the field on reads and strips it from writes, because the column does
 * not exist yet. Phase 2 flips that flag and deletes the store; nothing here or in
 * the screens changes shape.
 */
import { apiFetch } from '@/lib/api';
import {
  USE_UOM_DECIMAL_PLACES_MOCKS,
  rememberDecimalPlaces,
  stripDecimalPlaces,
  withDecimalPlaces,
  withDecimalPlacesList,
} from '../lib/uomDecimalPlacesMockStore';
import type { UnitOfMeasure, UOMFormData } from '../types/uom.types';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';

export async function getUOMs(params: DataGridApiFetchParams): Promise<DataGridApiResponse<UnitOfMeasure>> {
  const { pageIndex, pageSize, sorting, searchQuery } = params;
  const sortField = sorting?.[0]?.id || '';
  const sortDirection = sorting?.[0]?.desc ? 'desc' : 'asc';
  const queryParams = new URLSearchParams({
    page: String(pageIndex + 1),
    limit: String(pageSize),
    ...(sortField ? { sort: sortField, dir: sortDirection } : {}),
    ...(searchQuery ? { query: searchQuery } : {}),
  });
  const response = await apiFetch(`/api/v1/master-data/units-of-measure?${queryParams.toString()}`);
  if (!response.ok) throw new Error('Failed to fetch UOMs');
  const body = (await response.json()) as DataGridApiResponse<UnitOfMeasure>;
  return { ...body, data: withDecimalPlacesList(body.data) };
}

export async function getUOM(id: string): Promise<UnitOfMeasure> {
  const response = await apiFetch(`/api/v1/master-data/units-of-measure/${id}`);
  if (!response.ok) throw new Error('Failed to fetch UOM');
  return withDecimalPlaces((await response.json()) as UnitOfMeasure);
}

export async function createUOM(data: UOMFormData): Promise<UnitOfMeasure> {
  const response = await apiFetch('/api/v1/master-data/units-of-measure', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(USE_UOM_DECIMAL_PLACES_MOCKS ? stripDecimalPlaces(data) : data),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to create UOM' }));
    throw new Error(error.message);
  }
  const created = (await response.json()) as UnitOfMeasure;
  if (USE_UOM_DECIMAL_PLACES_MOCKS) rememberDecimalPlaces(created.id, data.decimal_places);
  return withDecimalPlaces(created);
}

export async function updateUOM(id: string, data: Partial<UOMFormData>): Promise<UnitOfMeasure> {
  const response = await apiFetch(`/api/v1/master-data/units-of-measure/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(USE_UOM_DECIMAL_PLACES_MOCKS ? stripDecimalPlaces(data) : data),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to update UOM' }));
    throw new Error(error.message);
  }
  const updated = (await response.json()) as UnitOfMeasure;
  if (USE_UOM_DECIMAL_PLACES_MOCKS) rememberDecimalPlaces(id, data.decimal_places);
  return withDecimalPlaces(updated);
}

export async function deleteUOM(id: string): Promise<void> {
  const response = await apiFetch(`/api/v1/master-data/units-of-measure/${id}`, { method: 'DELETE' });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Failed to delete UOM' }));
    throw new Error(error.message);
  }
}
