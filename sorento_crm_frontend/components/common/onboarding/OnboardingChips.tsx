'use client';

/**
 * The three chip families the onboarding grid renders.
 *
 * They are deliberately separate visual vocabularies because they answer
 * different questions and a reader must not confuse them:
 *
 * - a **problem** is something the parser could not read (amber, the requester
 *   can fix it),
 * - a **collision** is something that already exists (blue, nobody needs to fix
 *   it - the lane will be skipped),
 * - a **lane** is what provisioning did (green / red / grey).
 */

import { AlertTriangle, Check, Info, Loader, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import type { OnboardingCollision, OnboardingLaneStep } from './types';

export function ProblemChips({ problems }: { problems: string[] }) {
  if (!problems.length) return null;
  return (
    <div className="flex flex-wrap gap-1">
      {problems.map((problem) => (
        <span
          key={problem}
          title={problem}
          className="inline-flex items-center gap-1 rounded-md bg-amber-100 px-1.5 py-0.5 text-xs text-amber-800"
        >
          <AlertTriangle className="size-3 shrink-0" />
          <span className="truncate max-w-[140px]">{problem}</span>
        </span>
      ))}
    </div>
  );
}

export function CollisionChips({ collisions }: { collisions: OnboardingCollision[] }) {
  if (!collisions.length) {
    return <span className="text-xs text-muted-foreground">None</span>;
  }
  return (
    <div className="flex flex-wrap gap-1">
      {collisions.map((collision) => (
        <span
          key={`${collision.kind}:${collision.label}`}
          title={collision.label}
          className="inline-flex items-center gap-1 rounded-md bg-sky-100 px-1.5 py-0.5 text-xs text-sky-800"
        >
          <Info className="size-3 shrink-0" />
          <span className="truncate max-w-[160px]">{collision.label}</span>
        </span>
      ))}
    </div>
  );
}

const LANE_TONE: Record<OnboardingLaneStep, string> = {
  pending: 'bg-gray-100 text-gray-600',
  done: 'bg-emerald-100 text-emerald-800',
  linked: 'bg-emerald-100 text-emerald-800',
  pushed: 'bg-emerald-100 text-emerald-800',
  created_local: 'bg-amber-100 text-amber-800',
  awaiting_invite: 'bg-amber-100 text-amber-800',
  skipped: 'bg-gray-200 text-gray-600',
  failed: 'bg-red-100 text-red-800',
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
  const title = detail ? `${label}: ${step} - ${detail}` : `${label}: ${step}`;
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs ${LANE_TONE[step] ?? LANE_TONE.pending}`}
    >
      <Icon className="size-3 shrink-0" />
      <span className="font-medium">{label}</span>
      {detail ? <span className="truncate max-w-[150px]">{detail}</span> : null}
    </span>
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
