import type { ServiceJobStatus } from '../types/serviceJob.types';

export type NextStepAction =
  | 'confirm'
  | 'assign'
  | 'on_the_way'
  | 'arrived'
  | 'completed'
  | 'verified';

export interface NextStep {
  action: NextStepAction;
  label: string;
}

export interface SecondaryMove {
  to: ServiceJobStatus;
  label: string;
  needsReason: boolean;
}

/** The one filled button on a job: its next step, or null when the job is finished. */
export function nextStepFor(job: {
  status: ServiceJobStatus;
  technician_id: string | null;
}): NextStep | null {
  switch (job.status) {
    case 'proposed':
      return { action: 'confirm', label: 'Confirm date' };
    case 'confirmed':
      return job.technician_id
        ? { action: 'on_the_way', label: 'On the way' }
        : { action: 'assign', label: 'Assign technician' };
    case 'on_the_way':
      return { action: 'arrived', label: 'Arrived' };
    case 'arrived':
      return { action: 'completed', label: 'Complete' };
    case 'completed':
      return { action: 'verified', label: 'Verify' };
    default:
      return null;
  }
}

const SECONDARY: Record<ServiceJobStatus, SecondaryMove[]> = {
  proposed: [{ to: 'cancelled', label: 'Cancel', needsReason: true }],
  confirmed: [
    { to: 'arrived', label: 'Arrived', needsReason: false },
    { to: 'proposed', label: 'Customer rejected the visit', needsReason: true },
    { to: 'cancelled', label: 'Cancel', needsReason: true },
  ],
  on_the_way: [{ to: 'proposed', label: 'Customer rejected the visit', needsReason: true }],
  arrived: [{ to: 'proposed', label: 'Revisit needed', needsReason: true }],
  completed: [{ to: 'arrived', label: 'Reopen: work not accepted', needsReason: false }],
  verified: [],
  cancelled: [],
};

/** The graph moves a status still allows besides its main step (gear and right-click menus). */
export function secondaryMoves(status: ServiceJobStatus, hasTechnician = true): SecondaryMove[] {
  // Arriving needs a technician, so it is never offered without one.
  return (SECONDARY[status] ?? []).filter((m) => hasTechnician || m.to !== 'arrived' || status === 'completed');
}

/** The status the main step moves the job to (assign and confirm do not move through transition). */
export const STEP_TARGET: Partial<Record<NextStepAction, ServiceJobStatus>> = {
  on_the_way: 'on_the_way',
  arrived: 'arrived',
  completed: 'completed',
  verified: 'verified',
};
