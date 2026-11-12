'use client';

/**
 * The project import run's action set (D15): Open, Revert, Delete.
 *
 * Built once here and rendered by both surfaces: the run page's gear (`DetailActions`) and the
 * runs list's right-click menu (`RunContextMenuItems`), so an action can never be reachable
 * from one and missing from the other. Revert is offered on an imported run, Delete on a run
 * that left nothing in the CRM (draft, previewed, reverted); both need `projects.import.run`
 * and ask nothing (D7): they park on the server and the countdown takes over the primary
 * button on the run page, or a toast over the list.
 */

import { ExternalLink, RotateCcw, Trash2 } from 'lucide-react';
import { ContextMenuItem } from '@/components/ui/context-menu';
import DeferredActionButton from '@/components/common/DeferredActionButton';
import { orderRecordActions, type RecordAction, type RecordActionSet } from '@/components/common/recordActions';
import { useDeferredAction } from '@/hooks/useDeferredAction';
import { useHasPermission } from '@/hooks/usePermissions';
import {
  PROJECT_IMPORT_RUN_KEY,
  PROJECT_IMPORT_RUNS_KEY,
  RUN_PERMISSION,
} from '../_shared/hooks/useProjectImport';
import type { ProjectImportStatus } from '../_shared/types/projectImport.types';

interface RunRef {
  id: string;
  run_no: string;
  status: ProjectImportStatus;
}

export interface UseProjectImportRunActionsOptions {
  /** Where a countdown goes: the run page's primary slot, or a toast over the list. */
  surface?: 'inline' | 'toast';
  /** The list row offers Open; the run page does not (it is the run). */
  onOpen?: () => void;
  /** Called once a delete has landed (the run page goes back to the list). */
  onDeleted?: () => void;
}

const DELETABLE: ProjectImportStatus[] = ['draft', 'previewed', 'reverted'];

export function useProjectImportRunActions(
  run: RunRef | undefined | null,
  { surface = 'inline', onOpen, onDeleted }: UseProjectImportRunActionsOptions = {},
): RecordActionSet {
  const canRun = useHasPermission(RUN_PERMISSION);
  const revertable = canRun && run?.status === 'imported';
  const deletable = canRun && !!run && DELETABLE.includes(run.status);

  const reverting = useDeferredAction({
    actionKey: 'project_import_run.revert',
    entityType: 'project_import_run',
    entityId: revertable ? run?.id : null,
    verb: 'Reverting',
    subject: run?.run_no ?? '',
    surface,
    watchFromMount: surface === 'inline',
    successMessage: 'Import reverted',
    // The History reads the run's audit trail: refreshed when the revert lands (D7).
    invalidateKeys: [
      [PROJECT_IMPORT_RUN_KEY, run?.id],
      [PROJECT_IMPORT_RUNS_KEY],
      ['audit-logs', 'project_import_run', run?.id],
    ],
  });
  const deleting = useDeferredAction({
    actionKey: 'project_import_run.delete',
    entityType: 'project_import_run',
    entityId: deletable ? run?.id : null,
    verb: 'Deleting',
    subject: run?.run_no ?? '',
    surface,
    watchFromMount: surface === 'inline',
    successMessage: 'Import deleted',
    invalidateKeys: [[PROJECT_IMPORT_RUNS_KEY]],
    onCommitted: onDeleted,
  });

  const actions: RecordAction[] = [];
  if (!run) return { actions, dialogs: null, pending: null };

  if (onOpen) {
    actions.push({ key: 'project_import_run.open', label: 'Open', icon: ExternalLink, run: onOpen });
  }
  if (revertable) {
    actions.push({
      key: 'project_import_run.revert',
      label: 'Revert',
      icon: RotateCcw,
      kind: 'destructive',
      disabled: reverting.isBlocked,
      run: () => reverting.start(),
    });
  }
  if (deletable) {
    actions.push({
      key: 'project_import_run.delete',
      label: 'Delete',
      icon: Trash2,
      kind: 'destructive',
      disabled: deleting.isBlocked,
      run: () => deleting.start(),
    });
  }

  // The run page's countdown slot (DetailActions `pendingAction`); a list row has none.
  const pending =
    surface !== 'inline' ? null : revertable ? (
      <DeferredActionButton
        pending={reverting.pending}
        verb="Reverting"
        subject={run.run_no}
        onCancel={reverting.cancel}
      />
    ) : deletable && deleting.pending ? (
      <DeferredActionButton
        pending={deleting.pending}
        verb="Deleting"
        subject={run.run_no}
        onCancel={deleting.cancel}
      />
    ) : null;

  return { actions, dialogs: null, pending };
}

/** The same action set as right-click menu items, in the gear's order. */
export function RunContextMenuItems({ actions }: { actions: RecordAction[] }) {
  const { secondary, destructive } = orderRecordActions(actions);
  return (
    <>
      {[...secondary, ...destructive].map((action) => (
        <ContextMenuItem
          key={action.key}
          variant={action.kind === 'destructive' ? 'destructive' : 'default'}
          disabled={action.disabled}
          onSelect={() => void action.run()}
        >
          {action.label}
        </ContextMenuItem>
      ))}
    </>
  );
}
