/**
 * Saved accessories box designs (PRICETAG-ACCESSORY-DESIGNER), under
 * `/api/v1/dealer-kit/accessory-templates`. Same gates as tag sizes: `dealer_kit.tag_templates.view`
 * reads, `.manage` writes.
 *
 *   GET    ""            -> AccessoryTemplateRecord[] ordered by name
 *   POST   ""            { name, design } -> record, 201 (409 DUPLICATE_NAME)
 *   GET    /{id}         -> record
 *   GET    /{id}/usage   -> { templates: { id, name }[] }
 *   PUT    /{id}         { name?, design? } -> record with `rewritten`: a new design is written into
 *                        every linked box in every tag template
 *   DELETE /{id}         -> 204 (the deferred `accessory_box_preset.delete` calls the same service)
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type { AccessoryDesign } from '@/lib/dealer-kit/accessory-card';

const BASE = '/api/v1/dealer-kit/accessory-templates';

export interface AccessoryTemplateRecord {
  id: string;
  name: string;
  design: AccessoryDesign;
  /** Tag templates carrying a box linked to this design. */
  used_in: number;
  created_by_name: string | null;
  created_at: string;
  updated_at: string;
  rewritten?: number;
}

export interface AccessoryTemplateInput {
  name: string;
  design: AccessoryDesign;
}

export interface AccessoryTemplateUsage {
  templates: { id: string; name: string }[];
}

const JSON_HEADERS = { 'Content-Type': 'application/json' };

export async function listAccessoryTemplates(): Promise<AccessoryTemplateRecord[]> {
  const response = await apiFetch(BASE);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load accessories templates'));
  }
  return response.json();
}

export async function getAccessoryTemplate(id: string): Promise<AccessoryTemplateRecord> {
  const response = await apiFetch(`${BASE}/${encodeURIComponent(id)}`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load the accessories template'));
  }
  return response.json();
}

export async function getAccessoryTemplateUsage(id: string): Promise<AccessoryTemplateUsage> {
  const response = await apiFetch(`${BASE}/${encodeURIComponent(id)}/usage`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load where it is used'));
  }
  return response.json();
}

export async function createAccessoryTemplate(
  input: AccessoryTemplateInput,
): Promise<AccessoryTemplateRecord> {
  const response = await apiFetch(BASE, {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify(input),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to save the accessories template'));
  }
  return response.json();
}

export async function updateAccessoryTemplate(
  id: string,
  input: Partial<AccessoryTemplateInput>,
): Promise<AccessoryTemplateRecord> {
  const response = await apiFetch(`${BASE}/${encodeURIComponent(id)}`, {
    method: 'PUT',
    headers: JSON_HEADERS,
    body: JSON.stringify(input),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to update the accessories template'));
  }
  return response.json();
}
