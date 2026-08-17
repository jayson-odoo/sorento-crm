'use client';

/**
 * The two chip families the onboarding grid renders.
 *
 * They answer different questions and a reader must not confuse them, so each
 * takes a different shared `Badge` variant rather than a hand-rolled pastel
 * class:
 *
 * - a **collision** is something that already exists (info, nobody needs to fix
 *   it - the lane will be skipped),
 * - a **lane** is what provisioning did (success / destructive / secondary).
 */

import { Check, Info, Loader, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import type { OnboardingCollision, OnboardingLaneStep } from './types';

export function CollisionChips({ collisions }: { collisions: OnboardingCollision[] }) {
  if (!collisions.length) {
    return <span className="text-xs text-muted-foreground">None</span>;
  }
  return (
    <div className="flex flex-wrap gap-1">
      {collisions.map((collision) => (
        <Badge
          key={`${collision.kind}:${collision.label}`}
          variant="info"
          appearance="light"
          size="sm"
          title={collision.label}
        >
          <Info />
          <span className="truncate max-w-[160px]">{collision.label}</span>
        </Badge>
      ))}
    </div>
  );
}

type BadgeVariant = 'success' | 'warning' | 'destructive' | 'secondary';

const LANE_VARIANT: Record<OnboardingLaneStep, BadgeVariant> = {
  pending: 'secondary',
  done: 'success',
  linked: 'success',
  pushed: 'success',
  created_local: 'warning',
  awaiting_invite: 'warning',
  skipped: 'secondary',
  failed: 'destructive',
};

const LANE_ICON: Record<OnboardingLaneStep, typeof Check> = {
  pending: Loader,
  done: Check,
  linked: Check,
  pushed: Check,
  created_local: Loader,
  awaiting_invite: Loader,
  skipped: Info,
  failed: X,
};

/**
 * What each lane step means in words.
 *
 * The tooltip used to interpolate the raw step, so hovering a half-provisioned
 * contact read "created_local" - an enum code leaking into the UI, which tells
 * a reviewer nothing about whether he has to act.
 */
export const LANE_STEP_LABELS: Record<OnboardingLaneStep, string> = {
  pending: 'Not started',
  done: 'Done',
  linked: 'Linked',
  pushed: 'Pushed',
  created_local: 'Created here, not yet pushed',
  awaiting_invite: 'Waiting on an invite',
  skipped: 'Skipped, it already exists',
  failed: 'Failed',
};

export interface LaneChipProps {
  label: string;
  step: OnboardingLaneStep;
  error?: string | null;
  /** Extra note, e.g. the name of the user this row matched. */
  note?: string | null;
  /**
   * True for lanes this release does not run yet (contact, agent seat). A
   * `pending` lane then reads "not yet automated" instead of implying that
   * something was tried and is still running - see UAC AC-7.6.
   */
  deferred?: boolean;
}

export function LaneChip({ label, step, error, note, deferred }: LaneChipProps) {
  const Icon = LANE_ICON[step] ?? Loader;
  const detail = error || note || (deferred && step === 'pending' ? 'Not yet automated' : null);
  const stepLabel = LANE_STEP_LABELS[step] ?? LANE_STEP_LABELS.pending;
  const title = detail ? `${label}: ${stepLabel} - ${detail}` : `${label}: ${stepLabel}`;
  return (
    <Badge
      variant={LANE_VARIANT[step] ?? 'secondary'}
      appearance="light"
      size="sm"
      title={title}
    >
      <Icon />
      <span className="font-medium">{label}</span>
      {detail ? <span className="truncate max-w-[150px]">{detail}</span> : null}
    </Badge>
  );
}

export function ReviewStatusBadge({ status }: { status: string }) {
  if (status === 'approved') {
    return (
      <Badge variant="success" appearance="ghost">
        Approved
      </Badge>
    );
  }
  if (status === 'rejected') {
    return (
      <Badge variant="destructive" appearance="ghost">
        Rejected
      </Badge>
    );
  }
  if (status === 'on_hold') {
    return (
      <Badge variant="warning" appearance="ghost">
        On hold
      </Badge>
    );
  }
  return (
    <Badge variant="secondary" appearance="ghost">
      Proposed
    </Badge>
  );
}
