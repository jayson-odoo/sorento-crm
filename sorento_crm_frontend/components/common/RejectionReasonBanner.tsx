'use client';

import { AlertCircle } from 'lucide-react';

/**
 * Red alert banner shown at the top of an entity detail page when the form is
 * rejected, surfacing WHY it was rejected. Mirrors the amber SlaEscalationBanner
 * placement (top, under the header) and the portal's destructive rejection
 * styling, so internal staff see the reason without scrolling.
 *
 * Render only when the entity is actually rejected — caller gates on the status
 * field. Renders nothing if no reason text is present.
 */
export function RejectionReasonBanner({ reason }: { reason?: string | null }) {
  if (!reason || !reason.trim()) return null;
  return (
    <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm text-destructive">
      <AlertCircle className="mt-0.5 size-4 shrink-0" />
      <p className="min-w-0">
        <span className="font-medium">Rejected</span>
        <span> — {reason.trim()}</span>
      </p>
    </div>
  );
}
