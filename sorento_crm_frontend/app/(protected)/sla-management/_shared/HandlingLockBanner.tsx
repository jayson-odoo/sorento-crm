'use client';

import { useState } from 'react';
import { Hand, HandHelping, Info, Lock } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import type { HandlingLockState, HandlingLockTracker } from './handlingLock';
import { TakeOverConfirmDialog } from './HandlingLockActions';

/** "since <time>" suffix — formats the raw naive-UTC string in Malaysia time (no Date round-trip). */
function sinceLabel(handledAt?: string | null): string {
  if (!handledAt) return '';
  const when = formatDateTimeInMalaysia(handledAt);
  return when ? ` since ${when}` : '';
}

/**
 * Guided handling-lock banner (PLAN §5). Renders above the business-CTA row of each
 * form detail. Presentational: the claim / take-over / release side effects are owned
 * by the caller (Phase 1 stubs, Phase 2 real mutations). Take-over routes through a
 * confirm dialog before firing (P1-9).
 *
 * Renders nothing when `state === 'not_escalated'` (today's behaviour, no lock).
 */
export function HandlingLockBanner({
  state,
  tracker,
  onClaim,
  onTakeOver,
}: {
  state: HandlingLockState;
  tracker: HandlingLockTracker | null;
  onClaim: () => void;
  onTakeOver: () => void;
}) {
  const [takeOverOpen, setTakeOverOpen] = useState(false);

  if (state === 'not_escalated') return null;

  const tier = tracker?.current_tier ?? null;
  const tierText = tier != null ? `Tier ${tier}` : 'a higher tier';
  const handlerName = tracker?.handled_by_name?.trim() || 'Someone';
  const since = sinceLabel(tracker?.handled_at);

  const shellClass =
    'flex flex-col gap-2 rounded-md border px-3 py-2.5 text-sm sm:flex-row sm:items-center sm:justify-between';

  if (state === 'unclaimed') {
    return (
      <div
        className={`${shellClass} border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-700/60 dark:bg-amber-950/40 dark:text-amber-200`}
        data-testid="handling-lock-banner"
      >
        <p className="flex items-start gap-2 min-w-0">
          <Lock className="mt-0.5 size-4 shrink-0" />
          <span>
            <span className="font-medium">Escalated to {tierText}</span> — no one handling
            yet. Claim it to act on this form.
          </span>
        </p>
        <Button size="sm" className="shrink-0 w-fit" onClick={onClaim}>
          <Hand className="size-4 mr-1" />
          Claim
        </Button>
      </div>
    );
  }

  if (state === 'mine') {
    return (
      <div
        className={`${shellClass} border-emerald-300 bg-emerald-50 text-emerald-900 dark:border-emerald-700/60 dark:bg-emerald-950/40 dark:text-emerald-200`}
        data-testid="handling-lock-banner"
      >
        <p className="flex items-start gap-2 min-w-0">
          <HandHelping className="mt-0.5 size-4 shrink-0" />
          <span>
            <span className="font-medium">You&apos;re handling this{since}</span>. Unclaim
            it from the actions menu to let someone else handle.
          </span>
        </p>
      </div>
    );
  }

  if (state === 'other_holds' || state === 'admin_other_holds') {
    return (
      <div
        className={`${shellClass} border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-700/60 dark:bg-amber-950/40 dark:text-amber-200`}
        data-testid="handling-lock-banner"
      >
        <p className="flex items-start gap-2 min-w-0">
          <Lock className="mt-0.5 size-4 shrink-0" />
          <span>
            <span className="font-medium">
              {handlerName} is handling this{since}
            </span>
            . Take over to act on this form.
          </span>
        </p>
        <Button
          size="sm"
          variant="outline"
          className="shrink-0 w-fit"
          onClick={() => setTakeOverOpen(true)}
        >
          <HandHelping className="size-4 mr-1" />
          Take over handling
        </Button>
        <TakeOverConfirmDialog
          open={takeOverOpen}
          onOpenChange={setTakeOverOpen}
          handlerName={tracker?.handled_by_name}
          onConfirm={onTakeOver}
        />
      </div>
    );
  }

  if (state === 'admin_unclaimed') {
    return (
      <div
        className={`${shellClass} border-border bg-muted/40 text-muted-foreground`}
        data-testid="handling-lock-banner"
      >
        <p className="flex items-start gap-2 min-w-0">
          <Info className="mt-0.5 size-4 shrink-0" />
          <span>
            Escalated to {tierText} — not yet claimed. You can act as admin.
          </span>
        </p>
      </div>
    );
  }

  // not_eligible — read-only, no button.
  return (
    <div
      className={`${shellClass} border-border bg-muted/40 text-muted-foreground`}
      data-testid="handling-lock-banner"
    >
      <p className="flex items-start gap-2 min-w-0">
        <Lock className="mt-0.5 size-4 shrink-0" />
        <span>
          Escalated to {tierText}, handled by{' '}
          <span className="font-medium">{handlerName}</span>.
        </span>
      </p>
    </div>
  );
}
