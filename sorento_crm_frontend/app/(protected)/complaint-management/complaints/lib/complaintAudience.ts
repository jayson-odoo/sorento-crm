/**
 * Which set of fields a complaint actually means.
 *
 * Retail and project complaints are the SAME entity: one table, one status graph, one
 * set of SLA stages, one dispatch board, one technician. What differs is which columns
 * carry a fact. A complaint lodged from the consumer portal has a Site address and a
 * pin and no Delivery Order Number; a project complaint has a DO number, a salesperson
 * and a project title and no Site. Rendering both sets on both cases gives every screen
 * a column of dashes, and a dash is ambiguous in the worst way - "blank because retail"
 * looks identical to "blank because nobody filled it in".
 *
 * So this is a presentation rule, deliberately kept out of the components that use it:
 * the detail page, the edit form and the list have to agree about what a complaint is,
 * and three copies of the same conditional would not stay in agreement.
 *
 * The discriminator is `reported_by_role`, which the portal and the WhatsApp intake
 * both stamp. It is null on every row that predates it, and null means project: those
 * rows are the existing book of work and they carry DO numbers and project titles.
 */

/** The five values `complaints.reported_by_role` may hold. Mirrors the backend's
 *  `party_service.REPORTED_BY_ROLES`, which is closed for the same reason. */
export const REPORTED_BY_LABELS: Record<string, string> = {
  end_user: 'End user',
  dealer: 'Dealer',
  salesperson: 'Salesperson',
  cs: 'Customer service',
  technician: 'Technician',
};

export type ComplaintAudience = 'retail' | 'project';

/** The roles that report a fault about a thing somebody owns, rather than about a
 *  delivery on a project. A dealer reporting for a walk-in customer is retail: the
 *  case has a Site and a receipt, not a DO number and a project title. */
const RETAIL_ROLES = new Set(['end_user', 'dealer']);

export function complaintAudience(
  complaint: { reported_by_role?: string | null } | null | undefined,
): ComplaintAudience {
  const role = (complaint?.reported_by_role || '').trim();
  return RETAIL_ROLES.has(role) ? 'retail' : 'project';
}

export function isRetailComplaint(
  complaint: { reported_by_role?: string | null } | null | undefined,
): boolean {
  return complaintAudience(complaint) === 'retail';
}

export function reportedByLabel(role?: string | null): string | null {
  const key = (role || '').trim();
  if (!key) return null;
  // An unknown value is shown as itself rather than swallowed: a role that reaches the
  // UI without a label here is a vocabulary drift worth seeing, not worth hiding.
  return REPORTED_BY_LABELS[key] ?? key;
}

/** The address a technician is dispatched to, assembled from the parts.
 *
 * Prefers the composed `site_address` the backend already wrote, because that is the
 * exact string every document prints; falls back to assembling the parts so a row whose
 * composed line was never written (or was cleared by a later edit) still shows an
 * address rather than nothing.
 */
export function siteAddressLines(complaint: {
  site_address?: string | null;
  site_address_line1?: string | null;
  site_address_line2?: string | null;
  site_postcode?: string | null;
  site_city?: string | null;
  site_state?: string | null;
  site_country?: string | null;
}): string[] {
  const lines = [
    complaint.site_address_line1,
    complaint.site_address_line2,
    [complaint.site_postcode, complaint.site_city].filter(Boolean).join(' '),
    complaint.site_state,
    complaint.site_country,
  ]
    .map((part) => (part || '').trim())
    .filter(Boolean);
  if (lines.length > 0) return lines;
  const composed = (complaint.site_address || '').trim();
  return composed ? [composed] : [];
}

/** The pin, formatted for display, or null when there is none.
 *
 * Coordinates arrive as strings (the backend serializes a Decimal, so the value does not
 * round-trip through a float) and Number() on an empty string is 0, which would put a
 * pin off the coast of Africa.
 */
export function formatPin(
  latitude: number | string | null | undefined,
  longitude: number | string | null | undefined,
): string | null {
  const lat = typeof latitude === 'string' ? latitude.trim() : latitude;
  const lng = typeof longitude === 'string' ? longitude.trim() : longitude;
  if (lat === null || lat === undefined || lat === '') return null;
  if (lng === null || lng === undefined || lng === '') return null;
  const latNum = Number(lat);
  const lngNum = Number(lng);
  if (!Number.isFinite(latNum) || !Number.isFinite(lngNum)) return null;
  return `${latNum.toFixed(5)}, ${lngNum.toFixed(5)}`;
}

/** A Google Maps link for the pin, so a dispatcher can open it without copying digits. */
export function pinMapsUrl(
  latitude: number | string | null | undefined,
  longitude: number | string | null | undefined,
): string | null {
  const pin = formatPin(latitude, longitude);
  if (!pin) return null;
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(pin.replace(/\s/g, ''))}`;
}
