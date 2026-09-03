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
// PHASE 1 MOCK - `apiFetch`/`extractApiError`/`BASE` come back with the real
// calls in Phase 2; every function below reads the in-memory array instead.

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

// ---------------------------------------------------------------------------
// PHASE 1 MOCK - swapped for apiFetch in Phase 2, and this whole block goes
// with it. Held in module scope so create/update/delete are visible across
// every mounted consumer (the listing page and the request designer's Tag
// Size control) for the length of one tab's session, which is enough to
// verify the flow end to end before the real table exists.
// ---------------------------------------------------------------------------

const MOCK_DELAY_MS = 250;

function mockDelay(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, MOCK_DELAY_MS));
}

let mockSizes: TagSizeRecord[] = [
  {
    id: 'mock-size-shelf-rail',
    name: 'Shelf rail',
    width_mm: 95,
    height_mm: 44.5,
    created_by: 'mock-user',
    created_by_name: 'Jayson',
    created_at: '2026-09-01T02:00:00',
    updated_at: '2026-09-01T02:00:00',
  },
  {
    id: 'mock-size-hanging-tag',
    name: 'Hanging tag',
    width_mm: 60,
    height_mm: 90,
    created_by: 'mock-user',
    created_by_name: 'Jayson',
    created_at: '2026-09-01T02:00:00',
    updated_at: '2026-09-01T02:00:00',
  },
];
let mockSeq = 1;

function duplicateNameError(name: string): Error {
  return new Error(`A tag size named "${name}" already exists.`);
}

/** PHASE 1 MOCK - swapped for apiFetch in Phase 2. */
export async function listTagSizes(): Promise<TagSizeRecord[]> {
  await mockDelay();
  return [...mockSizes].sort((a, b) => a.name.localeCompare(b.name));
}

/** PHASE 1 MOCK - swapped for apiFetch in Phase 2. */
export async function createTagSize(input: TagSizeInput): Promise<TagSizeRecord> {
  await mockDelay();
  const name = input.name.trim();
  if (mockSizes.some((s) => s.name.toLowerCase() === name.toLowerCase())) {
    throw duplicateNameError(name);
  }
  const row: TagSizeRecord = {
    id: `mock-size-${mockSeq++}`,
    name,
    width_mm: input.width_mm,
    height_mm: input.height_mm,
    created_by: 'mock-user',
    created_by_name: 'You',
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
  mockSizes = [...mockSizes, row];
  return row;
}

/** PHASE 1 MOCK - swapped for apiFetch in Phase 2. */
export async function updateTagSize(
  id: string,
  input: Partial<TagSizeInput>,
): Promise<TagSizeRecord> {
  await mockDelay();
  const existing = mockSizes.find((s) => s.id === id);
  if (!existing) throw new Error('Tag size not found');
  const name = input.name !== undefined ? input.name.trim() : existing.name;
  if (
    input.name !== undefined &&
    mockSizes.some((s) => s.id !== id && s.name.toLowerCase() === name.toLowerCase())
  ) {
    throw duplicateNameError(name);
  }
  const updated: TagSizeRecord = {
    ...existing,
    ...input,
    name,
    updated_at: new Date().toISOString(),
  };
  mockSizes = mockSizes.map((s) => (s.id === id ? updated : s));
  return updated;
}

/** PHASE 1 MOCK - swapped for apiFetch in Phase 2. */
export async function deleteTagSize(id: string): Promise<void> {
  await mockDelay();
  mockSizes = mockSizes.filter((s) => s.id !== id);
}
