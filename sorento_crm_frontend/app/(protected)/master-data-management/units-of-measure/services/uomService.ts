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
 * - **`0..4`, validated on every write.** Outside that range is rejected. It is
 *     canonical UOM divisibility - `EA` is 0 and refuses `2.5`, `kg` at 3 accepts
 *     it - not SCM arithmetic precision, and it is never inferred from
 *     `conversion_factor`.
 * - **Omitted on CREATE resolves to `0`**, the same fallback a missing rollout
 *     value takes. **Omitted on EDIT preserves the stored value**, so a partial
 *     update cannot silently reset a measure unit to whole numbers.
 * - **The backfill classifies by NAME, never by code.** Count names get 0;
 *     measure names get the greatest fractional scale actually observed in the
 *     transaction columns, capped at 4; every unknown name gets 0. A unit coded
 *     `EA` but named `Kilogram` is therefore a measure unit, and no historical
 *     quantity is rewritten.
 * - **SCM freezes it per run.** Each summary row copies the product's value as
 *     `uom_decimal_places` at calculation, and validation and allocation read that
 *     snapshot, so editing a unit here never changes a run already calculated.
 *
 * Live since slice S2-BE-1 (migration `374_uom_decimal_places`). The Phase-1 mock
 * store that overlaid the field is deleted; the field now travels on the real
 * payload in both directions, and no screen changed shape.
 */
import { apiFetch } from '@/lib/api';
import { buildDataGridParams, extractApiError } from '@/lib/api-client';
import type { UnitOfMeasure, UOMFormData } from '../types/uom.types';
import type { DataGridApiFetchParams, DataGridApiResponse } from '@/components/ui/data-grid';

export async function getUOMs(params: DataGridApiFetchParams): Promise<DataGridApiResponse<UnitOfMeasure>> {
  const queryParams = buildDataGridParams(params);
  const response = await apiFetch(`/api/v1/master-data/units-of-measure?${queryParams.toString()}`);
  if (!response.ok) throw new Error('Failed to fetch UOMs');
  return (await response.json()) as DataGridApiResponse<UnitOfMeasure>;
}

export async function getUOM(id: string): Promise<UnitOfMeasure> {
  const response = await apiFetch(`/api/v1/master-data/units-of-measure/${id}`);
  if (!response.ok) throw new Error('Failed to fetch UOM');
  return (await response.json()) as UnitOfMeasure;
}

export async function createUOM(data: UOMFormData): Promise<UnitOfMeasure> {
  const response = await apiFetch('/api/v1/master-data/units-of-measure', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to create UOM'));
  return (await response.json()) as UnitOfMeasure;
}

export async function updateUOM(id: string, data: Partial<UOMFormData>): Promise<UnitOfMeasure> {
  const response = await apiFetch(`/api/v1/master-data/units-of-measure/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to update UOM'));
  return (await response.json()) as UnitOfMeasure;
}

export async function deleteUOM(id: string): Promise<void> {
  const response = await apiFetch(`/api/v1/master-data/units-of-measure/${id}`, { method: 'DELETE' });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to delete UOM'));
}
