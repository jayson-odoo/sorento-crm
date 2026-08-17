'use client';

import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';

/**
 * An outcome is a STATUS, so it wears the system's status pill.
 *
 * It used to render as a bordered `outline` badge, which reads as a BUTTON: "Open" in a box
 * beside a real pill looks like the thing you click to open the record. It is a state, not
 * an action - and the row itself is what opens the record.
 *
 * Mapped onto the shared palette's existing keys rather than given colours of its own, the
 * same way sales-order statuses are: open is live work, won is a finished good outcome,
 * lost is a refusal, dormant is parked. A key the palette does not know falls back to grey,
 * which is how these four looked before.
 */
const PALETTE_KEY: Record<string, string> = {
  open: 'submitted',
  won: 'processed_by_cs',
  lost: 'rejected',
  dormant: 'closed',
};

const LABEL: Record<string, string> = {
  open: 'Open',
  won: 'Won',
  lost: 'Lost',
  dormant: 'Dormant',
};

export function OutcomePill({ outcome }: { outcome?: string | null }) {
  const key = (outcome ?? '').trim().toLowerCase();
  if (!key) return <span className="text-muted-foreground">-</span>;
  return (
    <span className={`${STATUS_PILL_BASE} ${statusPillClass(PALETTE_KEY[key] ?? key)}`}>
      {LABEL[key] ?? outcome}
    </span>
  );
}
