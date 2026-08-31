/**
 * Single source of truth for price tag request status presentation (label + pill colour).
 * Used by the CRM listing/detail and the portal so the status code + colour always tally.
 */

export const PRICE_TAG_STATUS_PILL_CLASS: Record<string, string> = {
  new: 'bg-sky-100 text-sky-800',
  designing: 'bg-amber-100 text-amber-800',
  proof_ready: 'bg-indigo-100 text-indigo-800',
  changes_requested: 'bg-orange-100 text-orange-800',
  approved: 'bg-blue-100 text-blue-800',
  ready: 'bg-emerald-100 text-emerald-800',
  rejected: 'bg-red-100 text-red-800',
  void: 'bg-slate-200 text-slate-700',
  draft: 'bg-muted text-muted-foreground',
};

const PRICE_TAG_STATUS_LABEL: Record<string, string> = {
  new: 'New',
  designing: 'Designing',
  proof_ready: 'Proof Ready',
  changes_requested: 'Changes Requested',
  approved: 'Approved',
  ready: 'Ready',
  rejected: 'Rejected',
  void: 'Void',
  draft: 'Draft',
};

export function priceTagStatusPillClass(status?: string | null): string {
  return (
    PRICE_TAG_STATUS_PILL_CLASS[(status ?? '').toLowerCase()] ??
    'bg-muted text-muted-foreground'
  );
}

export function priceTagStatusLabel(status?: string | null): string {
  const s = (status ?? '').trim().toLowerCase();
  if (!s) return '';
  if (PRICE_TAG_STATUS_LABEL[s]) return PRICE_TAG_STATUS_LABEL[s];
  return s
    .split(/[_\s]+/)
    .map((w) => (w ? w.charAt(0).toUpperCase() + w.slice(1) : ''))
    .join(' ');
}
