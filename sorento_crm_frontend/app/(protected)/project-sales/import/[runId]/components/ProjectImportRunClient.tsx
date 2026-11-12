'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import AuditTrail from '@/components/audit/AuditTrail';
import DeferredActionButton from '@/components/common/DeferredActionButton';
import DetailActions from '@/components/common/DetailActions';
import { PageHeader } from '@/components/common/PageHeader';
import { WizardSteps } from '@/components/common/WizardSteps';
import { useDeferredAction } from '@/hooks/useDeferredAction';
import { useHasPermission } from '@/hooks/usePermissions';
import {
  PROJECT_IMPORT_RUN_KEY,
  PROJECT_IMPORT_RUNS_KEY,
  PROJECT_IMPORT_RUNS_PAGER,
  RUN_PERMISSION,
  useProjectImportMutations,
  useProjectImportRun,
} from '../../../_shared/hooks/useProjectImport';
import type {
  ProjectImportKind,
  ProjectImportLineKey,
  ProjectImportRun,
} from '../../../_shared/types/projectImport.types';
import { RunStatusBadge } from '../../components/importLabels';
import { ColumnsStep } from './ColumnsStep';
import { PreviewStep } from './PreviewStep';
import { ResultsView } from './ResultsView';
import { ValuesStep } from './ValuesStep';

const STEPS = [
  { id: 'columns', label: 'Columns' },
  { id: 'values', label: 'Values' },
  { id: 'preview', label: 'Preview' },
  { id: 'import', label: 'Import' },
] as const;

type StepId = (typeof STEPS)[number]['id'];
type TabId = Exclude<StepId, 'import'> | 'history';

/** AC-PI-45: the step a run opens on, read off its status. */
export function stepForRun(run: ProjectImportRun): StepId {
  if (run.status === 'draft') return run.missing_columns.length > 0 ? 'columns' : 'values';
  if (run.status === 'previewed') return 'preview';
  return 'import';
}

/** One run (AC-PI-45..48): header, steps, and the step the run stands on. */
export function ProjectImportRunClient({ runId }: { runId: string }) {
  const runQuery = useProjectImportRun(runId);
  const run = runQuery.data;
  const canRun = useHasPermission(RUN_PERMISSION);
  const [tab, setTab] = React.useState<TabId | null>(null);
  const [kind, setKind] = React.useState<ProjectImportKind>('customer');
  const [focusLine, setFocusLine] = React.useState<ProjectImportLineKey | null>(null);
  const { preview, importRun } = useProjectImportMutations(runId);

  const router = useRouter();
  const revertable = canRun && run?.status === 'imported';
  const deletable =
    canRun && (run?.status === 'draft' || run?.status === 'previewed' || run?.status === 'reverted');
  const reverting = useDeferredAction({
    actionKey: 'project_import_run.revert',
    entityType: 'project_import_run',
    entityId: revertable ? runId : null,
    verb: 'Reverting',
    subject: run?.run_no ?? '',
    surface: 'inline',
    watchFromMount: true,
    successMessage: 'Import reverted',
    // The History reads the run's audit trail: refreshed when the revert lands (D7).
    invalidateKeys: [
      [PROJECT_IMPORT_RUN_KEY, runId],
      [PROJECT_IMPORT_RUNS_KEY],
      ['audit-logs', 'project_import_run', runId],
    ],
  });

  // Delete (round 9): the same parked-action wiring as revert, for a run that left nothing in
  // the CRM; the page goes back to the list once it lands.
  const deleting = useDeferredAction({
    actionKey: 'project_import_run.delete',
    entityType: 'project_import_run',
    entityId: deletable ? runId : null,
    verb: 'Deleting',
    subject: run?.run_no ?? '',
    surface: 'inline',
    watchFromMount: true,
    successMessage: 'Import deleted',
    invalidateKeys: [[PROJECT_IMPORT_RUNS_KEY]],
    onCommitted: () => router.push('/project-sales/import'),
  });

  // A status change (preview, import, revert) moves the page to the step it now stands on.
  const status = run?.status;
  const missing = run?.missing_columns.length ?? 0;
  React.useEffect(() => {
    setTab(null);
  }, [status, missing]);

  if (runQuery.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }
  if (!run) {
    return (
      <div className="space-y-3 py-10 text-center">
        <p className="text-sm font-semibold">This import could not be loaded</p>
        <Button variant="outline" onClick={() => void runQuery.refetch()}>
          Try again
        </Button>
      </div>
    );
  }

  const step = stepForRun(run);
  const editable = run.status === 'draft' || run.status === 'previewed';
  const current: TabId = tab ?? (step === 'import' ? 'values' : step);

  // One main button on every tab (D2, round 9): Columns has its own Next; Values runs the
  // preview; on Preview and History the run's next step is the header's (Import once
  // previewed, Preview while a draft).
  const previewButton = (
    <Button onClick={() => preview.mutate()} disabled={preview.isPending}>
      Preview
    </Button>
  );
  const importButton = (
    <Button onClick={() => importRun.mutate()} disabled={importRun.isPending}>
      Import
    </Button>
  );
  const primary =
    !canRun || !editable || current === 'columns'
      ? undefined
      : current === 'values'
        ? previewButton
        : step === 'preview'
          ? importButton
          : step === 'values'
            ? previewButton
            : undefined;

  const header = (
    <PageHeader
      title={
        <span className="flex flex-wrap items-center gap-2">
          <span>{run.run_no}</span>
          <RunStatusBadge status={run.status} />
        </span>
      }
      crumbTitle={run.run_no}
      crumbs={[
        { title: 'Project Sales' },
        { title: 'Project import', path: '/project-sales/import' },
        { title: run.run_no },
      ]}
      actions={
        <div className="flex min-w-0 flex-wrap items-center justify-end gap-2">
          {/* The file this run read (owner ruling #1336: no subtitle slot on PageHeader). */}
          <span
            className="max-w-[16rem] truncate text-sm text-muted-foreground"
            title={run.filename ?? ''}
          >
            {run.filename}
          </span>
          <DetailActions
            pager={{
              ...PROJECT_IMPORT_RUNS_PAGER,
              detailPath: '/project-sales/import',
              currentId: runId,
              ariaLabel: 'import',
            }}
            actions={
              revertable
                ? [
                    {
                      key: 'project_import_run.revert',
                      label: 'Revert',
                      kind: 'destructive',
                      disabled: reverting.isBlocked,
                      run: () => reverting.start(),
                    },
                  ]
                : deletable
                  ? [
                      {
                        key: 'project_import_run.delete',
                        label: 'Delete',
                        kind: 'destructive',
                        disabled: deleting.isBlocked,
                        run: () => deleting.start(),
                      },
                    ]
                  : undefined
            }
            pendingAction={
              revertable ? (
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
              ) : undefined
            }
            primary={primary}
          />
        </div>
      }
    />
  );

  return (
    <div className="space-y-5">
      {header}
      <WizardSteps steps={STEPS} currentId={step} allDone={run.status === 'imported'} />
      {run.error && (
        <div role="alert" className="rounded-lg border border-destructive/40 p-3 text-sm">
          {run.error}
        </div>
      )}
      {step === 'import' ? (
        <ResultsView run={run} />
      ) : (
        <Tabs value={current} onValueChange={(next) => setTab(next as TabId)} className="space-y-4">
          <TabsList variant="line" className="w-full justify-start">
            <TabsTrigger value="columns">Columns</TabsTrigger>
            <TabsTrigger value="values" disabled={run.missing_columns.length > 0}>
              Values
            </TabsTrigger>
            <TabsTrigger value="preview" disabled={run.status !== 'previewed'}>
              Preview
            </TabsTrigger>
            <TabsTrigger value="history">History</TabsTrigger>
          </TabsList>
          <TabsContent value="columns">
            <ColumnsStep run={run} onSaved={() => setTab('values')} />
          </TabsContent>
          <TabsContent value="values">
            <ValuesStep
              run={run}
              kind={kind}
              onKindChange={(next) => {
                setKind(next);
                setFocusLine(null);
              }}
              readOnly={!editable}
              focusLine={focusLine}
            />
          </TabsContent>
          <TabsContent value="preview">
            <PreviewStep
              run={run}
              onOpenLine={(next, line) => {
                setKind(next);
                setFocusLine(line ?? null);
                setTab('values');
              }}
            />
          </TabsContent>
          <TabsContent value="history">
            <AuditTrail entityType="project_import_run" entityId={run.id} />
          </TabsContent>
        </Tabs>
      )}
    </div>
  );
}

export default ProjectImportRunClient;
