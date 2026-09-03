/**
 * ============================================================================
 * API CONTRACT - tag size presets (S4, PLAN D2, AC-S4-1/2)
 * ============================================================================
 *
 * Company-scoped named tag sizes: presets the request designer's Tag Size
 * control offers under "Saved sizes" (`request-tags.ts`'s own `tagSizePresets`
 * stays the "Template sizes" group - published templates, not deletable here)
 * and the record a marketing user manages at `/dealer-kit/tag-sizes`. Gated
 * behind the SAME permission the tag template routes use (D9) - no new slug:
 *
 *   GET    /api/v1/dealer-kit/tag-sizes
 *     -> TagSizeRecord[]                          dealer_kit.tag_templates.view
 *   POST   /api/v1/dealer-kit/tag-sizes
 *     { name, width_mm, height_mm } -> TagSizeRecord, 201
 *     dealer_kit.tag_templates.manage. A duplicate name (per company) is 409
 *     { code: 'DUPLICATE_NAME' }; width/height below 10mm is 422.
 *   PUT    /api/v1/dealer-kit/tag-sizes/{id}
 *     { name?, width_mm?, height_mm? } -> TagSizeRecord
 *     dealer_kit.tag_templates.manage. Same duplicate/validation rules.
 *   DELETE /api/v1/dealer-kit/tag-sizes/{id} -> 204
 *     dealer_kit.tag_templates.manage. The immediate delete - the listing's
 *     row delete and the tag-size control's saved-size delete both go through
 *     the deferred-action pending-actions flow (`tag_size_preset.delete`),
 *     which calls this same service method on commit, exactly the
 *     relationship `tag_template.delete` already has with its own route
 *     (`tag_templates.py`).
 * ============================================================================
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

const BASE = '/api/v1/dealer-kit/tag-sizes';

/** A saved tag size, as the API answers it. Not `TagSizePreset` (`request-tags.ts`
 *  already owns that name for a dropdown OPTION, template-derived or saved). */
export interface TagSizeRecord {
  id: string;
  name: string;
  width_mm: number;
  height_mm: number;
  created_by: string | null;
  created_by_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface TagSizeInput {
  name: string;
  width_mm: number;
  height_mm: number;
}

export async function listTagSizes(): Promise<TagSizeRecord[]> {
  const response = await apiFetch(BASE);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load tag sizes'));
  }
  return response.json();
}

export async function createTagSize(input: TagSizeInput): Promise<TagSizeRecord> {
  const response = await apiFetch(BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to create tag size'));
  }
  return response.json();
}

export async function updateTagSize(
  id: string,
  input: Partial<TagSizeInput>,
): Promise<TagSizeRecord> {
  const response = await apiFetch(`${BASE}/${encodeURIComponent(id)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to update tag size'));
  }
  return response.json();
}

/** The immediate delete - see the API contract banner above for who calls it. */
export async function deleteTagSize(id: string): Promise<void> {
  const response = await apiFetch(`${BASE}/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to delete tag size'));
  }
}
