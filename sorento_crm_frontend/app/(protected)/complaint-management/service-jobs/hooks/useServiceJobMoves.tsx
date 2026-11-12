'use client';

import { useState, type ReactNode } from 'react';
import { nextStepFor, STEP_TARGET, type NextStep, type SecondaryMove } from '../lib/nextStep';
import type { ServiceJob } from '../types/serviceJob.types';
import { useServiceJobActions } from './useServiceJobs';
import ConfirmDateDialog from '../components/ConfirmDateDialog';
import AssignTechnicianDialog from '../components/AssignTechnicianDialog';
import ReasonDialog from '../components/ReasonDialog';

type Dialog =
  | { kind: 'confirm'; job: ServiceJob }
  | { kind: 'assign'; job: ServiceJob }
  | { kind: 'reason'; job: ServiceJob; move: SecondaryMove }
  | null;

/**
 * Runs a job's moves: the main step and the gear / right-click moves. A move that needs more
 * than a click (a date, a technician, a reason) opens its centred dialog; the others go straight
 * to the server. The caller mounts `dialogs` once.
 */
export function useServiceJobMoves(): {
  runStep: (job: ServiceJob, step: NextStep) => void;
  runMove: (job: ServiceJob, move: SecondaryMove) => void;
  dialogs: ReactNode;
  isPending: boolean;
} {
  const { confirm, assign, transition } = useServiceJobActions();
  const [dialog, setDialog] = useState<Dialog>(null);
  const close = () => setDialog(null);

  const runStep = (job: ServiceJob, step: NextStep) => {
    if (step.action === 'confirm') return setDialog({ kind: 'confirm', job });
    if (step.action === 'assign') return setDialog({ kind: 'assign', job });
    const to = STEP_TARGET[step.action];
    if (to) transition.mutate({ id: job.id, values: { to } });
  };

  const runMove = (job: ServiceJob, move: SecondaryMove) => {
    if (move.needsReason) return setDialog({ kind: 'reason', job, move });
    transition.mutate({ id: job.id, values: { to: move.to } });
  };

  const dialogs = (
    <>
      <ConfirmDateDialog
        open={dialog?.kind === 'confirm'}
        onOpenChange={(o) => !o && close()}
        initialScheduledFrom={dialog?.kind === 'confirm' ? dialog.job.scheduled_from ?? undefined : undefined}
        isPending={confirm.isPending}
        onSubmit={(values) => {
          if (dialog?.kind !== 'confirm') return;
          confirm.mutate({ id: dialog.job.id, values }, { onSuccess: close });
        }}
      />
      {dialog?.kind === 'assign' && (
        <AssignTechnicianDialog
          open
          onOpenChange={(o) => !o && close()}
          currentTechnicianId={dialog.job.technician_id}
          isPending={assign.isPending}
          onSubmit={(technicianId) =>
            assign.mutate({ id: dialog.job.id, technicianId }, { onSuccess: close })
          }
        />
      )}
      <ReasonDialog
        open={dialog?.kind === 'reason'}
        onOpenChange={(o) => !o && close()}
        title={dialog?.kind === 'reason' ? dialog.move.label : ''}
        isPending={transition.isPending}
        onSubmit={(reason) => {
          if (dialog?.kind !== 'reason') return;
          transition.mutate(
            { id: dialog.job.id, values: { to: dialog.move.to, reason } },
            { onSuccess: close },
          );
        }}
      />
    </>
  );

  return { runStep, runMove, dialogs, isPending: confirm.isPending || assign.isPending || transition.isPending };
}

export { nextStepFor };
