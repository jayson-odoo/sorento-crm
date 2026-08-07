/**
 * Portal path helpers — slug-aware navigation.
 *
 * Every portal page lives under the contact's stable URL `/portal/c/{slug}`
 * once the slug is known. Legacy `/portal/...` paths remain as thin
 * redirectors for old links. All in-app navigation MUST go through these
 * helpers so the active tree (slug vs legacy) is picked in one place.
 *
 * The active slug is persisted in localStorage so it survives tab close —
 * it is an identity hint, not a credential (entry still requires a live
 * token or OTP).
 */

const SLUG_KEY = 'sorento.portalSlug';

export function readPortalSlug(): string | null {
  if (typeof window === 'undefined') return null;
  return window.localStorage.getItem(SLUG_KEY);
}

export function writePortalSlug(slug: string): void {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(SLUG_KEY, slug);
}

export function clearPortalSlug(): void {
  if (typeof window === 'undefined') return;
  window.localStorage.removeItem(SLUG_KEY);
}

/**
 * Base path for the active tree: `/portal/c/{slug}` or legacy `/portal`.
 *
 * Tri-state slug argument:
 * - string  → that contact's tree
 * - undefined (omitted) → fall back to the stored slug
 * - null    → FORCE the legacy tree. Critical for token-recovery redirects:
 *   a foreign `?token=` must never be hijacked onto this device's stored
 *   slug, or the verify page would show the wrong contact's identity.
 */
export function portalBase(slug?: string | null): string {
  const s = slug === undefined ? readPortalSlug() : slug;
  return s ? `/portal/c/${encodeURIComponent(s)}` : '/portal';
}

export function portalHomePath(opts: { slug?: string | null; type?: string | null } = {}): string {
  const base = portalBase(opts.slug);
  return opts.type && opts.type.trim()
    ? `${base}?type=${encodeURIComponent(opts.type.trim())}`
    : base;
}

export function portalVerifyPath(
  opts: {
    slug?: string | null;
    reason?: 'expired' | 'logout';
    token?: string | null;
    type?: string | null;
    /** Submission id from the deep link — forwarded so verify can land the user
     *  back on that exact form after the OTP, not just the type index. */
    id?: string | null;
  } = {},
): string {
  const base = portalBase(opts.slug);
  const qs = new URLSearchParams();
  if (opts.reason) qs.set('reason', opts.reason);
  // Legacy tree only: forward the (expired) token so /portal/verify can
  // recover contact/space via /token-info. The slug tree resolves identity
  // from the slug itself, no token needed.
  if (base === '/portal' && opts.token) qs.set('token', opts.token);
  if (opts.type && opts.type.trim()) qs.set('type', opts.type.trim());
  if (opts.id && opts.id.trim()) qs.set('id', opts.id.trim());
  const q = qs.toString();
  return `${base}/verify${q ? `?${q}` : ''}`;
}

export function portalNewPath(kind: string, slug?: string | null): string {
  return `${portalBase(slug)}/${kind}/new`;
}

/**
 * The S3 consumer intake journey - photo first, the system reads the rest.
 *
 * A SEPARATE door from `portalNewPath('complaint', slug)`, which is the typed dealer form.
 * They are not two versions of one screen: the form asks a dealer who knows their own order
 * numbers to type them, and this asks a consumer who knows nothing except what the fault
 * looks like to photograph it. Collapsing them would make one of those two people do the
 * other one's job.
 */
export function portalLodgePath(slug?: string | null): string {
  return `${portalBase(slug)}/lodge`;
}

export function portalDetailPath(kind: string, id: string, slug?: string | null): string {
  return `${portalBase(slug)}/${kind}/${encodeURIComponent(id)}`;
}

/** Build a WhatsApp click-to-chat URL with prefilled text. */
export function waMeUrl(phoneNumber: string, text: string): string {
  const digits = phoneNumber.replace(/\D/g, '');
  return `https://wa.me/${digits}?text=${encodeURIComponent(text)}`;
}
