/**
 * Tag template service.
 *
 * Calls `/api/v1/dealer-kit/tag-templates` via `apiFetch`.
 */

import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type {
  TagTemplate,
  TagTemplateDoc,
  TagTemplateFamily,
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
 * Find the first template whose family matches.
 *
 * Used by the tag sheet designer to auto-select a template when a request
 * line is dropped onto a sheet. Returns null when no matching template
 * exists (caller falls back to the generic ala_carte template).
 */
export async function getTemplateForFamily(
  family: TagTemplateFamily,
): Promise<TagTemplate | null> {
  const templates = await listTemplates();
  return templates.find((t) => t.family === family) ?? null;
}
