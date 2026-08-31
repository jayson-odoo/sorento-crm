/**
 * The portal form kinds and their labels - one list, read by both sides.
 *
 * The portal reads it to build its landing dropdown and its submission pages.
 * The CRM's Contact Access Types screen reads it to offer an admin the kinds it
 * may grant (D61b). They lived in `app/(auth)/portal/lib/portal-client.ts` until
 * the admin screen needed them; that module re-exports every name below, so the
 * portal's imports are unchanged and neither side can label a kind differently
 * from the other.
 *
 * Deliberately free of imports: an admin page under `(protected)` has no
 * business pulling in the portal's token storage and fetch helpers.
 */

export type PortalSubmissionKind =
  | 'complaint'
  | 'stock_inquiry'
  | 'purchase_request'
  | 'sponsorship_form';

/** Canonical kind list - single source for route guards, tab lists, labels. */
export const SUBMISSION_KINDS: readonly PortalSubmissionKind[] = [
  'complaint',
  'stock_inquiry',
  'purchase_request',
  'sponsorship_form',
] as const;

export function isSubmissionKind(
  value: string | null | undefined,
): value is PortalSubmissionKind {
  return (SUBMISSION_KINDS as readonly string[]).includes(value ?? '');
}

/**
 * Form types that join the landing dropdown beside the four legacy kinds, each
 * shown only to a contact whose `visible_form_types` grants it (D45).
 *
 * Deliberately NOT part of `SUBMISSION_KINDS`: that list is what the generic
 * `[type]` route guards read to decide what the shared submission pages may
 * render, and these forms have pages of their own. The next gated form joins
 * THIS list, plus a label below and a fetch in the landing's loader.
 */
export const GATED_LANDING_KINDS = ['price_tag_request'] as const;

export type PortalGatedKind = (typeof GATED_LANDING_KINDS)[number];

/** Everything the landing dropdown can offer, gated or not. */
export type PortalLandingKind = PortalSubmissionKind | PortalGatedKind;

/** Every kind an access type may be granted, in the order the admin sees them. */
export const LANDING_KINDS: readonly PortalLandingKind[] = [
  ...SUBMISSION_KINDS,
  ...GATED_LANDING_KINDS,
] as const;

export function isGatedLandingKind(
  value: string | null | undefined,
): value is PortalGatedKind {
  return (GATED_LANDING_KINDS as readonly string[]).includes(value ?? '');
}

export function isLandingKind(
  value: string | null | undefined,
): value is PortalLandingKind {
  return isSubmissionKind(value) || isGatedLandingKind(value);
}

export const SUBMISSION_LABELS: Record<PortalSubmissionKind, string> = {
  complaint: 'Complaint',
  stock_inquiry: 'Stock Inquiry',
  purchase_request: 'Purchase Request',
  sponsorship_form: 'Sponsorship Form',
};

/** Every kind the landing can list, legacy or gated (D45). */
export const LANDING_LABELS: Record<PortalLandingKind, string> = {
  ...SUBMISSION_LABELS,
  price_tag_request: 'Price Tag Request',
};

/** The label for any kind, falling back to the raw code for one we do not know. */
export function portalFormKindLabel(kind: string): string {
  return LANDING_LABELS[kind as PortalLandingKind] ?? kind;
}
