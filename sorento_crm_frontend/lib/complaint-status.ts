/**
 * Single source of truth for complaint status presentation (label + pill colour).
 * Used by the internal system view (ComplaintDetail) and the customer portal so
 * the status code + colour always tally across both.
 */

export const COMPLAINT_STATUS_PILL_CLASS: Record<string, string> = {
  draft: 'bg-muted text-muted-foreground',
  new: 'bg-muted text-muted-foreground',
  submitted: 'bg-sky-100 text-sky-800',
  updated: 'bg-amber-100 text-amber-800',
  responded: 'bg-indigo-100 text-indigo-800',
  approved: 'bg-blue-100 text-blue-800',
  rejected: 'bg-red-100 text-red-800',
  processed_by_cs: 'bg-emerald-100 text-emerald-800',
  resolved: 'bg-emerald-100 text-emerald-800',
  // Auto-fulfilment: complaint closed by a delivered replacement DO. Violet —
  // a non-green hue so the terminal "Fulfilled" state is unmistakably distinct
  // from the emerald processed_by_cs / resolved states.
  fulfilled: 'bg-violet-100 text-violet-800',
  // Terminal without customer service: the technician settled the issue during the
  // site visit, so no replacement DO exists. Teal keeps it distinct from both the
  // emerald CS states and the violet delivered-replacement state.
  settled_on_site: 'bg-teal-100 text-teal-800',
  closed: 'bg-slate-200 text-slate-700',
};

// Explicit labels where a simple title-case wouldn't read well.
const COMPLAINT_STATUS_LABEL: Record<string, string> = {
  processed_by_cs: 'Processed by CS',
  fulfilled: 'Fulfilled',
  settled_on_site: 'Settled on site',
};

export function complaintStatusPillClass(status?: string | null): string {
  return (
    COMPLAINT_STATUS_PILL_CLASS[(status ?? '').toLowerCase()] ??
    'bg-muted text-muted-foreground'
  );
}

export function complaintStatusLabel(status?: string | null): string {
  const s = (status ?? '').trim().toLowerCase();
  if (!s) return '';
  if (COMPLAINT_STATUS_LABEL[s]) return COMPLAINT_STATUS_LABEL[s];
  // Title-case snake_case / space-separated values (e.g. 'submitted' -> 'Submitted').
  return s
    .split(/[_\s]+/)
    .map((w) => (w ? w.charAt(0).toUpperCase() + w.slice(1) : ''))
    .join(' ');
}
