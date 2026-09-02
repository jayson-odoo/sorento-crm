'use client';

import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { useDrainingScaleXFill } from '@/hooks/useDrainingScaleXFill';
import type { PendingAction } from '@/services/pendingActionService';

/** Treat a timezone-less ISO timestamp (naive UTC from the backend) as UTC. */
function asUtc(iso: string): string {
  return /[zZ]|[+-]\d{2}:?\d{2}$/.test(iso) ? iso : `${iso}Z`;
}

export interface DeferredCountdownProps {
  /** The parked action, or null when nothing is running. */
  pending: PendingAction | null;
  /** Verb-first copy: "Deleting" reads as "Deleting in 8s". */
  verb: string;
  /** What the action is being done to, for the toast's second line. */
  subject?: string;
  onCancel: () => void;
  /** Disabled while the cancel request is in flight. */
  cancelling?: boolean;
  className?: string;
}

/**
 * The countdown that replaces the confirmation dialog (D7, S6-06).
 *
 * The bar drains against the SERVER's `commit_at`, never a local counter, so a
 * refresh or a tab switch cannot restart the window - and when the countdown
 * reaches zero the label says the action is being applied rather than pretending
 * it already is: the server, not this component, decides that.
 *
 * There is no Escape handler and no dialog: Escape must not cancel a pending
 * action (S6-08). Cancel is a button, and it is the only way back.
 */
export function DeferredCountdown({
  pending,
  verb,
  subject,
  onCancel,
  cancelling,
  className,
}: DeferredCountdownProps) {
  const target = pending ? Date.parse(asUtc(pending.commit_at)) : 0;
  const [now, setNow] = useState(() => Date.now());
  // The fill itself no longer needs a fast tick (see the transform effect
  // below) - this one only redraws the `role="timer"` label, so once a
  // second is plenty (M3-01).
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!pending) return;
    tickRef.current = setInterval(() => setNow(Date.now()), 1000);
    return () => {
      if (tickRef.current) clearInterval(tickRef.current);
    };
  }, [pending]);

  // The fill always parks fresh and full - an action is only ever just-parked,
  // never resumed partway through from a remount - so the ONE shared
  // draining mechanism (`hooks/useDrainingScaleXFill`, M3-01) always starts
  // it at scaleX(1) and drains to 0 by the server's `commit_at`.
  const fillStyle = useDrainingScaleXFill(target, 1);

  if (!pending) return null;

  const remainingMs = Math.max(0, target - now);
  const lapsed = remainingMs <= 0;
  const label = lapsed ? `${verb}…` : `${verb} in ${Math.ceil(remainingMs / 1000)}s`;

  return (
    <div
      data-testid="deferred-countdown"
      data-lapsed={lapsed ? 'true' : undefined}
      className={cn(
        'flex min-w-[13rem] flex-col gap-1.5 rounded-md border border-border bg-card px-3 py-2',
        className,
      )}
    >
      <div className="flex items-center gap-3">
        <span className="text-sm font-medium tabular-nums" role="timer">
          {label}
        </span>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="ms-auto h-7 px-2"
          onClick={onCancel}
          disabled={cancelling || lapsed}
        >
          Cancel
        </Button>
      </div>
      {subject && (
        <span className="truncate text-xs text-muted-foreground" title={subject}>
          {subject}
        </span>
      )}
      <div className="h-1 overflow-hidden rounded-full bg-muted">
        <div
          data-testid="deferred-countdown-bar"
          className={cn(
            'h-full origin-left rounded-full motion-reduce:transition-none',
            lapsed ? 'bg-muted-foreground/40' : 'bg-destructive',
          )}
          // Lapsed flatlines the bar full (matches the pre-M3 behaviour) rather
          // than letting the transition's own end value (scaleX(0), empty) show:
          // "the window is over" reads as a full grey bar, not a vanished one.
          style={lapsed ? { transform: 'scaleX(1)' } : fillStyle}
        />
      </div>
    </div>
  );
}

export interface DeferredActionButtonProps extends DeferredCountdownProps {
  /**
   * What stands here while nothing is parked - the record page's primary button,
   * or a Delete of its own. Omitted, the slot is empty until an action starts,
   * which is what a gear item wants: the gear is the trigger, this is the answer.
   */
  idle?: ReactNode;
}

/**
 * A button that becomes its own countdown.
 *
 * On a record page the trigger is the gear's Delete and this sits in the primary
 * area, so `idle` is the primary button and Cancel restores it (S6-06).
 */
export default function DeferredActionButton({
  idle,
  ...countdown
}: DeferredActionButtonProps) {
  if (!countdown.pending) return <>{idle ?? null}</>;
  return <DeferredCountdown {...countdown} />;
}
