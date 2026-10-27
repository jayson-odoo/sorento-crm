'use client';

import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
import { isAwaitingReview } from '@/lib/submission-status';
import type { ProjectApprovalState } from '../types/project.types';

const LABEL: Partial<Record<ProjectApprovalState, string>> = {
  pending: 'Awaiting approval',
  resubmitted: 'Resubmitted',
  rejected: 'Rejected',
};

/** True for a portal registration still waiting for, or refused, approval (R6). */
export function isAwaitingDecision(state?: ProjectApprovalState | null): boolean {
  return isAwaitingReview(state, 'pending') || state === 'rejected';
}

/**
 * Where a portal registration stands before it has a stage (PROJECT-REG-PORTAL R6): the
 * pill stands where the stage pill would. Nothing for a staff or an approved project.
 */
export function ApprovalStatePill({ state }: { state?: ProjectApprovalState | null }) {
  const label = state ? LABEL[state] : undefined;
  if (!label) return null;
  return <span className={`${STATUS_PILL_BASE} ${statusPillClass(state!)}`}>{label}</span>;
}
