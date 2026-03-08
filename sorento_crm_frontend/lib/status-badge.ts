/**
 * System-wide status color coding for list and detail status badges.
 * Use getStatusBadgeVariant(status) for consistent colors across the app.
 */

export type StatusBadgeVariant =
  | 'primary'
  | 'secondary'
  | 'success'
  | 'warning'
  | 'info'
  | 'outline'
  | 'destructive';

/** Normalized (lowercase, trimmed) status -> Badge variant */
const STATUS_VARIANT_MAP: Record<string, StatusBadgeVariant> = {
  // Success / completed / positive
  approved: 'success',
  completed: 'success',
  active: 'success',
  received: 'success',
  sent: 'success',
  responded: 'success',
  success: 'success',
  available: 'success',
  normal: 'success',
  finished: 'success',
  delivered: 'success',
  shipped: 'success',
  confirmed: 'success',
  posted: 'success',
  allowed: 'success',
  yes: 'success',

  // Warning / in progress / pending
  pending: 'warning',
  pending_approval: 'warning',
  draft: 'warning',
  new: 'warning',
  queued: 'warning',
  started: 'warning',
  in_progress: 'warning',
  in_transit: 'warning',
  allocated: 'info',
  partially_allocated: 'warning',
  reserved: 'warning',
  planning: 'warning',
  processing: 'warning',
  inactive: 'warning',
  returned: 'warning',
  critical: 'warning',
  arrived_at_port: 'info',
  at_warehouse: 'info',
  partially_received: 'info',
  partial_received: 'info',
  fully_received: 'success',

  // Info / updated / neutral-positive
  updated: 'info',
  submitted: 'info',
  overstock: 'secondary',

  // Destructive / negative
  rejected: 'destructive',
  failed: 'destructive',
  cancelled: 'destructive',
  expired: 'destructive',
  blocked: 'destructive',
  damaged: 'destructive',
  no: 'destructive',
  disallowed: 'destructive',

  // Secondary / neutral
  closed: 'secondary',
  low: 'destructive',
  skipped: 'secondary',
};

/**
 * Returns the Badge variant for a given status string.
 * Status is normalized (lowercase, trim, replace spaces with underscores) before lookup.
 * For unknown statuses, attempts keyword fallback (e.g. "Cancelled" -> destructive).
 */
export function getStatusBadgeVariant(status: string | null | undefined): StatusBadgeVariant {
  if (status == null || String(status).trim() === '') return 'secondary';
  const normalized = String(status)
    .trim()
    .toLowerCase()
    .replace(/\s+/g, '_');
  const exact = STATUS_VARIANT_MAP[normalized];
  if (exact) return exact;
  // Keyword fallback for dynamic status names (e.g. order status from API)
  if (/\b(cancel|reject|fail|expire|block|damage|denied)\b/.test(normalized)) return 'destructive';
  if (/\b(pending|draft|new|queue|progress|transit|reserv|plan)\b/.test(normalized)) return 'warning';
  if (/\b(approv|complet|receiv|sent|respond|success|active|deliver|ship|confirm|finish)\b/.test(normalized))
    return 'success';
  if (/\b(updat|submit)\b/.test(normalized)) return 'info';
  return 'secondary';
}

/**
 * Formats status for display: capitalize words, replace underscores with spaces.
 */
export function formatStatusLabel(status: string | null | undefined): string {
  if (status == null || String(status).trim() === '') return '—';
  return String(status)
    .trim()
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}
