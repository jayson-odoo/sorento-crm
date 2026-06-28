'use client';

import { useState } from 'react';
import { CalendarPlus } from 'lucide-react';

import { Button } from '@/components/ui/button';
import ExtendDueDialog from './ExtendDueDialog';

interface ExtendDueButtonProps {
  trackingId: string;
  /** Current resolution deadline (naive-UTC ISO). When undefined, the field is
   *  unknown on this surface (see gating notes); when null, there is no resolution
   *  deadline and the button is hidden. */
  currentDueAt?: string | null;
  /** Whether the row is resolved — Extend only applies to unresolved rows. */
  isResolved: boolean;
  /**
   * Whether the current user is the assignee. Extend is assignee-only (the backend
   * 403s otherwise). Pass `true` when the surface already guarantees ownership
   * (e.g. the "My Pending" widget only lists the viewer's own rows) and the
   * assignee id is not separately available.
   */
  isAssignee: boolean;
  /** A takeover is pending on this row — Extend is locked (mirrors Reassign). */
  takeoverPending?: boolean;
  /**
   * Controls how a missing (`undefined`) `currentDueAt` is treated:
   *  - 'require' (default): hide the button when the resolution due is unknown.
   *  - 'allow-unknown': show the button regardless; the dialog's preview confirms
   *    whether a resolution deadline exists. (Both surfaces now receive
   *    `due_at_resolution`, so 'require' is the norm; this remains for any future
   *    surface that lists trackers without the field.)
   */
  unknownDuePolicy?: 'require' | 'allow-unknown';
  label?: string;
  /** Forwarded to the dialog: fires after a successful extend. */
  onExtended?: () => void;
  size?: 'sm' | 'md';
  variant?: 'outline' | 'ghost';
  className?: string;
}

/**
 * Renders the Extend action only when gating passes:
 *   unresolved AND assignee AND no pending takeover AND has a resolution deadline.
 *
 * Shared across the My Pending widget and the in-form SLA banner (PR / stock
 * inquiry / complaint detail) so the gate and dialog never drift.
 */
export default function ExtendDueButton({
  trackingId,
  currentDueAt,
  isResolved,
  isAssignee,
  takeoverPending = false,
  unknownDuePolicy = 'require',
  label,
  onExtended,
  size = 'sm',
  variant = 'outline',
  className,
}: ExtendDueButtonProps) {
  const [open, setOpen] = useState(false);

  const hasResolutionDue =
    currentDueAt != null ||
    (currentDueAt === undefined && unknownDuePolicy === 'allow-unknown');

  const visible = !isResolved && isAssignee && !takeoverPending && hasResolutionDue;
  if (!visible) return null;

  return (
    <>
      <Button
        size={size === 'sm' ? 'sm' : 'md'}
        variant={variant}
        className={className ?? (size === 'sm' ? 'h-7' : undefined)}
        data-guide-target="dashboard.sla-tasks.extend"
        onClick={(e) => {
          e.stopPropagation();
          setOpen(true);
        }}
      >
        <CalendarPlus className="size-3.5" />
        Extend
      </Button>
      <ExtendDueDialog
        open={open}
        onOpenChange={setOpen}
        trackingId={trackingId}
        currentDueAt={currentDueAt ?? null}
        label={label}
        onExtended={onExtended}
      />
    </>
  );
}
