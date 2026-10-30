/**
 * Per-contact accessible brands (CONTACT-BRAND-SCOPE).
 *
 * Layering: UI (ContactBrandScopeSection) -> hook (useContactBrandScope) -> THIS service ->
 * lib/api -> backend.
 *
 *   GET /api/v1/user-management/contacts/{id}/brands
 *     -> { brand_ids, brands: [{ id, brand_name }],
 *          allowed_item_class_codes: string[],
 *          item_class_options: [{ code, name }] }   ("No class" = __NONE__, first)
 *   PUT /api/v1/user-management/contacts/{id}/brands
 *        body { brand_ids: string[], allowed_item_class_codes: string[] }
 *     -> the same shape. `[]` stores NULL = every brand / every class. An unknown brand id or
 *        class code is a 422 (TAG-BRAND-CLASS).
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

export interface ContactBrandRef {
  id: string;
  brand_name: string;
}

export interface ContactItemClassOption {
  code: string;
  name: string;
}

export interface ContactBrandScope {
  /** Empty = every brand. */
  brand_ids: string[];
  brands: ContactBrandRef[];
  /** Allowed item class codes; empty = every class. */
  allowed_item_class_codes?: string[];
  /** The picker's options, "No class" first. */
  item_class_options?: ContactItemClassOption[];
}

export interface ContactBrandScopeInput {
  brandIds: string[];
  allowedItemClassCodes: string[];
}

export const contactBrandScopeKey = (contactId: string) => ['contact-brand-scope', contactId];

const path = (contactId: string) =>
  `/api/v1/user-management/contacts/${encodeURIComponent(contactId)}/brands`;

export async function getContactBrandScope(contactId: string): Promise<ContactBrandScope> {
  const response = await apiFetch(path(contactId));
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load the contact brands'));
  }
  return response.json();
}

export async function saveContactBrandScope(
  contactId: string,
  { brandIds, allowedItemClassCodes }: ContactBrandScopeInput,
): Promise<ContactBrandScope> {
  const response = await apiFetch(path(contactId), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ brand_ids: brandIds, allowed_item_class_codes: allowedItemClassCodes }),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to save the contact brands'));
  }
  return response.json();
}
