import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

/**
 * Per-contact portal form visibility override (PLAN-contact-portal-form-override, UAC AC-1/AC-2).
 *
 * ---------------------------------------------------------------------------
 * API CONTRACT - written in Phase 1, built to in Phase 2
 * ---------------------------------------------------------------------------
 *
 * GET /api/v1/user-management/contacts/{contact_id}/portal-forms
 *   Permission: `user_management.contacts.view`.
 *   200 -> { "forms": [ { "form_type": "price_tag_request", "inherited": false,
 *                          "override": null, "effective": false } ] }
 *
 *   One row per GATED form kind only (today: price_tag_request). The four legacy
 *   submission kinds are always on the portal landing and never appear here.
 *   `inherited` = granted by the union of the contact's assigned access types.
 *   `override` = null (no row, inherits) | true (always show) | false (always hide).
 *   `effective` = override if set, else inherited.
 *
 * PUT /api/v1/user-management/contacts/{contact_id}/portal-forms
 *   Permission: `user_management.contacts.edit`.
 *   body: { "overrides": [ { "form_type": "price_tag_request", "is_enabled": true|false|null } ] }
 *     is_enabled null clears the override row (back to inherit).
 *   200 -> the same shape as GET, recomputed.
 *   422 for a form_type outside the gated set. 404 for an unknown contact.
 */

export interface ContactPortalFormRow {
  form_type: string;
  inherited: boolean;
  override: boolean | null;
  effective: boolean;
}

export interface ContactPortalForms {
  forms: ContactPortalFormRow[];
}

export async function getContactPortalForms(contactId: string): Promise<ContactPortalForms> {
  const response = await apiFetch(`/api/user-management/contacts/${contactId}/portal-forms`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load portal forms'));
  }
  return response.json();
}

export async function updateContactPortalForm(
  contactId: string,
  formType: string,
  isEnabled: boolean | null,
): Promise<ContactPortalForms> {
  const response = await apiFetch(`/api/user-management/contacts/${contactId}/portal-forms`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ overrides: [{ form_type: formType, is_enabled: isEnabled }] }),
  });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to save portal forms'));
  }
  return response.json();
}
