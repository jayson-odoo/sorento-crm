'use client';

import { AlertTriangle, Info, Undo2, XCircle } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { TakeoverCountdown } from '@/app/(protected)/sla-management/conversation-sla-tracking/components/TakeoverCountdown';
import type { FormActionView } from './formAction';

const SHELL =
  'flex flex-col gap-2 rounded-md border px-3 py-2.5 text-sm sm:flex-row sm:items-center sm:justify-between';
const AMBER =
  'border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-700/60 dark:bg-amber-950/40 dark:text-amber-200';
const RED =
  'border-destructive/40 bg-destructive/10 text-destructive dark:border-destructive/50';
const MUTED = 'border-border bg-muted/40 text-muted-foreground';

/**
 * The one banner that renders every form-action state (AC-U-7). Presentational only  - 
 * cancel / undo side effects belong to the caller, same split as HandlingLockBanner.
 *
 * Renders nothing in the `idle` and `undoable` states: `undoable` puts its affordance in
 * the actions menu, not in a banner, because there is nothing in flight to announce.
 */
export function FormActionBanner({
  view,
  onCancel,
  onExpire,
  onDismissOutcome,
  isCancelling = false,
}: {
  view: FormActionView;
  onCancel: () => void;
  /** Fired once when the countdown crosses zero, so the caller can poll for the outcome. */
  onExpire: () => void;
  onDismissOutcome: () => void;
  isCancelling?: boolean;
}) {
  // `undo_blocked` renders nothing: a committed action that can no longer be reversed
  // is the ordinary state of most forms, and announcing it on every page load is noise.
  // The reason still reaches the user - it is why the Undo action is absent from the
  // actions menu, and the server returns it if anyone calls undo anyway.
  if (view.kind === 'idle' || view.kind === 'undoable' || view.kind === 'undo_blocked') {
    return null;
  }

  if (view.kind === 'pending' || view.kind === 'committing') {
    const { action } = view;
    const committing = view.kind === 'committing';
    return (
      <div className={`${SHELL} ${AMBER}`} data-testid="form-action-banner">
        <div className="flex min-w-0 flex-1 flex-col gap-1.5">
          <p className="flex items-start gap-2 min-w-0">
            <Info className="mt-0.5 size-4 shrink-0" />
            <span>
              {committing
                ? 'Applying your action now.'
                : 'Undo to revert your action.'}
            </span>
          </p>
          <TakeoverCountdown
            commitAt={action.commit_at}
            windowSeconds={action.window_seconds}
            onExpire={onExpire}
            className="w-full"
          />
        </div>
        {action.can_cancel && !committing ? (
          <Button
            size="sm"
            variant="outline"
            className="shrink-0 w-fit"
            onClick={onCancel}
            disabled={isCancelling}
            data-testid="form-action-undo-pending"
          >
            <Undo2 className="size-4 mr-1" />
            Undo
          </Button>
        ) : null}
      </div>
    );
  }

  if (view.kind === 'ineligible') {
    return (
      <div className={`${SHELL} ${MUTED}`} data-testid="form-action-banner">
        <p className="flex items-start gap-2 min-w-0">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" />
          <span>
            <span className="font-medium">That action was not applied</span> - {view.reason}
          </span>
        </p>
        <Button size="sm" variant="ghost" className="shrink-0 w-fit" onClick={onDismissOutcome}>
          Dismiss
        </Button>
      </div>
    );
  }

  if (view.kind === 'failed') {
    return (
      <div className={`${SHELL} ${RED}`} data-testid="form-action-banner">
        <p className="flex items-start gap-2 min-w-0">
          <XCircle className="mt-0.5 size-4 shrink-0" />
          <span>
            <span className="font-medium">That action failed</span> - {view.reason}. The form
            is unchanged; try again.
          </span>
        </p>
        <Button size="sm" variant="ghost" className="shrink-0 w-fit" onClick={onDismissOutcome}>
          Dismiss
        </Button>
      </div>
    );
  }

  return null;
}

export default FormActionBanner;
