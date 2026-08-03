'use client';

import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';

/**
 * Where the project stands, as a read-only pill.
 *
 * The header used to carry an editable stage dropdown. A control that changes the state
 * of the whole record, sitting where a reader's eye lands first and looking like a filter,
 * is a trap: the client's words were "the ability for me to change status at the top right
 * is confusing". The stage moves through the one primary action beside it instead, which
 * only ever offers moves the status graph allows.
 *
 * Funnel keys are mapped onto the shared palette's existing keys rather than given a
 * palette of their own, exactly as the sales order pill does. A key nobody has mapped
 * (an admin invented their own rung) falls back to the neutral chip, never to a wrong
 * colour.
 */
const PALETTE_KEY: Record<string, string> = {
  identified: 'new',
  registered: 'submitted',
  specified: 'responded',
  quoted: 'approved',
  tendering: 'pending',
  po_received: 'processed_by_cs',
  lost: 'rejected',
  dormant: 'closed',
};

export function ProjectStatusPill({
  statusKey,
  label,
}: {
  statusKey?: string | null;
  label?: string | null;
}) {
  const key = statusKey ?? label ?? '';
  return (
    <span className={`${STATUS_PILL_BASE} ${statusPillClass(PALETTE_KEY[key] ?? key)}`}>
      {label ?? 'No stage set'}
    </span>
  );
}
