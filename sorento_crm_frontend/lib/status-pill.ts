/**
 * Shared soft-pastel status pill — the look used by Complaints, applied across
 * Purchase Requests / Sponsorship Forms / Stock Inquiries so every form status
 * pill reads the same. Mirrors the palette in lib/complaint-status.ts.
 *
 * Render: <span className={`${STATUS_PILL_BASE} ${statusPillClass(status)}`}>{label}</span>
 */
const STATUS_PILL_CLASS: Record<string, string> = {
  draft: 'bg-muted text-muted-foreground',
  new: 'bg-muted text-muted-foreground',
  submitted: 'bg-sky-100 text-sky-800',
  pending: 'bg-amber-100 text-amber-800',
  pending_approval: 'bg-amber-100 text-amber-800',
  pending_project_sales: 'bg-amber-100 text-amber-800',
  pending_purchasing: 'bg-amber-100 text-amber-800',
  updated: 'bg-amber-100 text-amber-800',
  responded: 'bg-indigo-100 text-indigo-800',
  approved: 'bg-blue-100 text-blue-800',
  rejected: 'bg-red-100 text-red-800',
  processed_by_cs: 'bg-emerald-100 text-emerald-800',
  resolved: 'bg-emerald-100 text-emerald-800',
  closed: 'bg-slate-200 text-slate-700',
  // A catalogue Edition that went live. Terminal and successful, so it reads
  // like resolved/processed rather than like closed, which is merely over.
  done: 'bg-emerald-100 text-emerald-800',
  // Voided = form was cancelled/annulled after creation. Neutral gray (muted),
  // deliberately NOT red — voiding is administrative, not an error/rejection.
  voided: 'bg-gray-200 text-gray-600',
};

/** Base classes for the pill chip (shape + sizing); pair with statusPillClass(). */
export const STATUS_PILL_BASE =
  'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold capitalize';

/** Pastel pill colour for a status. Accepts raw codes or display labels
 * ("Pending approval" -> pending_approval). Falls back to neutral. */
export function statusPillClass(status?: string | null): string {
  const s = (status ?? '').trim().toLowerCase().replace(/\s+/g, '_');
  return STATUS_PILL_CLASS[s] ?? 'bg-muted text-muted-foreground';
}
