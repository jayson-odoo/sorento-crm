/**
 * Tag template service.
 *
 * Calls `/api/v1/dealer-kit/tag-templates` via `apiFetch`.
 *
 * API contract (S5, PLAN D7/D15/D16 - versions + publish):
 *   GET    /tag-templates?published=1        -> TagTemplate[], PUBLISHED doc/print_size,
 *                                                only templates with a live pointer
 *   POST   /tag-templates/{id}/publish        { note? }        -> TagTemplate
 *   POST   /tag-templates/{id}/unpublish                        -> TagTemplate
 *   GET    /tag-templates/{id}/versions                          -> TagTemplateVersion[] (newest first)
 *   GET    /tag-templates/{id}/versions/{versionId}               -> TagTemplateVersionDetail
 *   POST   /tag-templates/{id}/versions/{versionId}/restore       -> TagTemplate (draft <- version doc)
 */

import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type {
  TagTemplate,
  TagTemplateDoc,
  TagTemplateFamily,
  TagTemplateVersion,
  TagTemplateVersionDetail,
} from '@/lib/dealer-kit/tag-template-types';

const BASE = '/api/v1/dealer-kit/tag-templates';

// ---------------------------------------------------------------------------
// Service functions
// ---------------------------------------------------------------------------

export async function listTemplates(): Promise<TagTemplate[]> {
  const response = await apiFetch(BASE);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load tag templates'));
  }
  return response.json();
}

export async function getTemplate(id: string): Promise<TagTemplate> {
  const response = await apiFetch(`${BASE}/${encodeURIComponent(id)}`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Tag template not found'));
  }
  return response.json();
}

export async function createTemplate(input: {
  name: string;
  family: TagTemplateFamily;
  print_size: { width_mm: number; height_mm: number };
}): Promise<TagTemplate> {
  const response = await apiFetch(BASE, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: input.name,
      family: input.family,
      doc: {
        width_mm: input.print_size.width_mm,
        height_mm: input.print_size.height_mm,
        layers: [],
      },
      print_size: input.print_size,
    }),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to create template'));
  }
  return response.json();
}

export async function updateTemplate(
  id: string,
  doc: TagTemplateDoc,
): Promise<TagTemplate> {
  const response = await apiFetch(`${BASE}/${encodeURIComponent(id)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ doc }),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to update template'));
  }
  return response.json();
}

export async function deleteTemplate(id: string): Promise<void> {
  const response = await apiFetch(`${BASE}/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to delete template'));
  }
}

/**
 * The request designer's template source (AC-S5-2): only templates with a
 * live pointer, and each one's PUBLISHED doc - never its draft, which keeps
 * changing underneath it the moment marketing edits after a publish.
 */
export async function listPublishedTemplates(): Promise<TagTemplate[]> {
  const response = await apiFetch(`${BASE}?published=1`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load tag templates'));
  }
  return response.json();
}

/**
 * Snapshot the draft into a new immutable version and move the live pointer
 * (AC-S5-1). Draft edits made after this call never change the live version.
 */
export async function publishTemplate(id: string, note?: string): Promise<TagTemplate> {
  const response = await apiFetch(`${BASE}/${encodeURIComponent(id)}/publish`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ note: note || undefined }),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to publish template'));
  }
  return response.json();
}

/**
 * Move the live pointer to nothing (AC-S5-3). The draft and every version row
 * are untouched; the template can be published again at any time.
 */
export async function unpublishTemplate(id: string): Promise<TagTemplate> {
  const response = await apiFetch(`${BASE}/${encodeURIComponent(id)}/unpublish`, {
    method: 'POST',
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to unpublish template'));
  }
  return response.json();
}

/** Every version of this template, newest first (AC-S5-6). */
export async function listTemplateVersions(id: string): Promise<TagTemplateVersion[]> {
  const response = await apiFetch(`${BASE}/${encodeURIComponent(id)}/versions`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load template versions'));
  }
  return response.json();
}

/** A past version's full document, for View (D16) - read-only on the canvas. */
export async function getTemplateVersion(
  id: string,
  versionId: string,
): Promise<TagTemplateVersionDetail> {
  const response = await apiFetch(
    `${BASE}/${encodeURIComponent(id)}/versions/${encodeURIComponent(versionId)}`,
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Version not found'));
  }
  return response.json();
}

/**
 * Copy a version's doc into the draft (AC-S5-6/D15). The live pointer is
 * untouched - restoring an old design is not the same act as publishing it.
 */
export async function restoreTemplateVersion(
  id: string,
  versionId: string,
): Promise<TagTemplate> {
  const response = await apiFetch(
    `${BASE}/${encodeURIComponent(id)}/versions/${encodeURIComponent(versionId)}/restore`,
    { method: 'POST' },
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to restore version'));
  }
  return response.json();
}
