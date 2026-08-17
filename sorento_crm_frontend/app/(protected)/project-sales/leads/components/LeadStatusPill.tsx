'use client';

import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';

/**
 * Where a lead stands, as a coloured pill.
 *
 * The header used to render the rung as a `secondary` Badge and the derived OUTCOME as an
 * `outline` Badge beside it, which produced two grey boxes reading "Qualified Qualified" on
 * a qualified lead and "Open New" on a fresh one. Two problems in one: an outlined chip
 * holding a verb-shaped word looks like a button, and the outcome is derived from the rung,
 * so showing both says the same thing twice.
 *
 * One pill now, for the rung, coloured. Funnel keys map onto the shared palette's existing
 * keys, exactly as the project and sales-order pills do, so red keeps meaning refused across
 * the whole product. An unmapped key falls back to neutral grey rather than to a wrong
 * colour.
 */
const PALETTE_KEY: Record<string, string> = {
  new: 'new',
  contacted: 'submitted',
  qualifying: 'pending',
  qualified: 'processed_by_cs',
  disqualified: 'rejected',
};

export function LeadStatusPill({
  statusKey,
  label,
}: {
  statusKey?: string | null;
  label?: string | null;
}) {
  const key = (statusKey ?? label ?? '').trim().toLowerCase();
  if (!label && !key) return <span className="text-muted-foreground">-</span>;
  return (
    <span className={`${STATUS_PILL_BASE} ${statusPillClass(PALETTE_KEY[key] ?? key)}`}>
      {label ?? 'No stage set'}
    </span>
  );
}
