'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import DeferredActionButton from '@/components/common/DeferredActionButton';
import DetailActions from '@/components/common/DetailActions';
import { PageHeader } from '@/components/common/PageHeader';
import RecordNavigation from '@/components/common/RecordNavigation';
import { WizardSteps } from '@/components/common/WizardSteps';
import { useDeferredAction } from '@/hooks/useDeferredAction';
import {
  PROJECT_IMPORT_RUN_KEY,
  PROJECT_IMPORT_RUNS_KEY,
  useProjectImportMutations,
  useProjectImportRun,
  useProjectImportRuns,
} from '../../../_shared/hooks/useProjectImport';
import type { ProjectImportKind, ProjectImportRun } from '../../../_shared/types/projectImport.types';
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

/** AC-PI-45: the step a run opens on, read off its status. */
export function stepForRun(run: ProjectImportRun): StepId {
  if (run.status === 'draft') return run.missing_columns.length > 0 ? 'columns' : 'values';
  if (run.status === 'previewed') return 'preview';
  return 'import';
}

/** One run (AC-PI-45..48): header, steps, and the step the run stands on. */
export function ProjectImportRunClient({ runId }: { runId: string }) {
  const router = useRouter();
  const runQuery = useProjectImportRun(runId);
  const run = runQuery.data;
  const [step, setStep] = React.useState<StepId | null>(null);
  const [kind, setKind] = React.useState<ProjectImportKind>('customer');
  const { preview } = useProjectImportMutations(runId);

  const runs = useProjectImportRuns({ pageIndex: 0, pageSize: 200, sorting: [{ id: 'uploaded_at', desc: true }] });
  const ids = (runs.data?.data ?? []).map((r) => r.id);
  const at = ids.indexOf(runId);

  const reverting = useDeferredAction({
    actionKey: 'project_import_run.revert',
    entityType: 'project_import_run',
    entityId: run?.status === 'imported' ? runId : null,
    verb: 'Reverting',
    subject: run?.run_no ?? '',
    surface: 'inline',
    watchFromMount: true,
    successMessage: 'Import reverted',
    invalidateKeys: [[PROJECT_IMPORT_RUN_KEY, runId], [PROJECT_IMPORT_RUNS_KEY]],
  });

  // A status change (preview, import, revert) moves the page to the step it now stands on.
  const status = run?.status;
  const missing = run?.missing_columns.length ?? 0;
  React.useEffect(() => {
    setStep(null);
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

  const current: StepId = step ?? stepForRun(run);
  const editable = run.status === 'draft' || run.status === 'previewed';

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
        <DetailActions
          pagerNode={
            <RecordNavigation
              index={at >= 0 ? at + 1 : null}
              total={ids.length}
              hasPrevious={at > 0}
              hasNext={at >= 0 && at < ids.length - 1}
              onPrevious={() => router.push(`/project-sales/import/${ids[at - 1]}`)}
              onNext={() => router.push(`/project-sales/import/${ids[at + 1]}`)}
              isLoading={runs.isLoading}
              ariaLabel="import"
            />
          }
          actions={
            run.status === 'imported'
              ? [
                  {
                    key: 'project_import_run.revert',
                    label: 'Revert',
                    kind: 'destructive',
                    disabled: reverting.isBlocked,
                    run: () => reverting.start(),
                  },
                ]
              : undefined
          }
          pendingAction={
            run.status === 'imported' ? (
              <DeferredActionButton
                pending={reverting.pending}
                verb="Reverting"
                subject={run.run_no}
                onCancel={reverting.cancel}
              />
            ) : undefined
          }
          primary={
            current === 'values' && editable ? (
              <Button onClick={() => preview.mutate()} disabled={preview.isPending}>
                Preview
              </Button>
            ) : undefined
          }
        />
      }
    />
  );

  return (
    <div className="space-y-5">
      {header}
      <p className="-mt-3 truncate text-sm text-muted-foreground" title={run.filename ?? ''}>
        {run.filename}
      </p>
      <WizardSteps steps={STEPS} currentId={current} allDone={run.status === 'imported'} />
      {editable && current !== 'import' && (
        <div className="flex flex-wrap gap-2">
          {STEPS.filter((s) => s.id !== 'import').map((s) => (
            <Button
              key={s.id}
              variant={s.id === current ? 'secondary' : 'ghost'}
              size="sm"
              disabled={s.id === 'preview' && run.status !== 'previewed'}
              onClick={() => setStep(s.id)}
            >
              {s.label}
            </Button>
          ))}
        </div>
      )}
      {current === 'columns' && <ColumnsStep run={run} />}
      {current === 'values' && <ValuesStep run={run} kind={kind} onKindChange={setKind} />}
      {current === 'preview' && (
        <PreviewStep
          run={run}
          onOpenLine={(next) => {
            setKind(next);
            setStep('values');
          }}
        />
      )}
      {current === 'import' && <ResultsView run={run} />}
    </div>
  );
}

export default ProjectImportRunClient;
