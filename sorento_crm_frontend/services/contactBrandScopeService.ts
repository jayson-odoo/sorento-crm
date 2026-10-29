/**
 * Per-contact accessible brands (CONTACT-BRAND-SCOPE).
 *
 * Layering: UI (ContactBrandScopeSection) -> hook (useContactBrandScope) -> THIS service ->
 * lib/api -> backend.
 *
 *   GET /api/v1/user-management/contacts/{id}/brands
 *     -> { brand_ids, brands: [{ id, brand_name }],
 *          brand_class_ids: { [brand_id]: class_id[] },
 *          item_classes: [{ id, item_class_name }] }
 *   PUT /api/v1/user-management/contacts/{id}/brands
 *        body { brand_ids: string[], brand_class_ids: { [brand_id]: class_id[] } }
 *     -> the same shape. Replaces the list; `[]` stores NULL = every brand. A brand absent from
 *        brand_class_ids (or mapped to []) means every class of that brand. Class lists for
 *        brands not in brand_ids are dropped server side. An unknown brand id is a 422.
 */
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

export interface ContactBrandRef {
  id: string;
  brand_name: string;
}

export interface ContactBrandScope {
  /** Empty = every brand. */
  brand_ids: string[];
  brands: ContactBrandRef[];
  /** brand id -> the item class ids the contact is narrowed to; absent or [] = every class. */
  brand_class_ids?: Record<string, string[]>;
  /** Names for the class ids in `brand_class_ids`. */
  item_classes?: ContactItemClassRef[];
}

export interface ContactItemClassRef {
  id: string;
  item_class_name: string;
}

export interface ContactBrandScopeInput {
  brandIds: string[];
  brandClassIds: Record<string, string[]>;
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
  { brandIds, brandClassIds }: ContactBrandScopeInput,
): Promise<ContactBrandScope> {
  const response = await apiFetch(path(contactId), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ brand_ids: brandIds, brand_class_ids: brandClassIds }),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to save the contact brands'));
  }
  return response.json();
}
