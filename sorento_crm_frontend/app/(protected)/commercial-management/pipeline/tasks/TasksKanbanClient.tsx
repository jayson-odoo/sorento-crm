'use client';

import * as React from 'react';
import { PipelineKanbanBoard } from '../components/PipelineKanbanBoard';
import { PipelineScopeFilters } from '../components/PipelineScopeFilters';
import {
  fetchKanbanTasks,
  fetchStageConfig,
  patchPipelineTaskStatus,
  type KanbanBoardPayload,
  type ScopeParam,
  type StageConfig,
} from '../services/commercialPipelineApi';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';

type TaskCard = {
  kind: string;
  id?: string;
  title: string;
  status_code: string;
  due_on?: string | null;
  due_at?: string | null;
  tender_code?: string | null;
  quotation_code?: string | null;
  lead_code?: string | null;
};

export function TasksKanbanClient() {
  const [scope, setScope] = React.useState<ScopeParam>('all');
  const [view, setView] = React.useState<'board' | 'overdue' | 'soon'>('board');
  const [board, setBoard] = React.useState<KanbanBoardPayload | null>(null);
  const [stages, setStages] = React.useState<StageConfig | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    setError(null);
    try {
      const [cfg, b] = await Promise.all([
        fetchStageConfig(),
        fetchKanbanTasks(scope, {
          overdue_only: view === 'overdue',
          due_soon_only: view === 'soon',
          include_activity: true,
        }),
      ]);
      setStages(cfg);
      setBoard(b);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load board');
    }
  }, [scope, view]);

  React.useEffect(() => {
    void load();
  }, [load]);

  const colTitle = React.useCallback(
    (code: string) => {
      if (code === '__none__') return 'Unassigned';
      const fromPipeline = stages?.pipeline_task_statuses.find((s) => s.code === code);
      if (fromPipeline) return fromPipeline.label;
      const fromActivity = stages?.activity_task_statuses.find((s) => s.code === code);
      return fromActivity?.label ?? code;
    },
    [stages],
  );

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertTitle>Error</AlertTitle>
        <AlertDescription>{error}</AlertDescription>
      </Alert>
    );
  }

  if (!board) return null;

  const cols = board.columns as Record<string, TaskCard[]>;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-4">
        <PipelineScopeFilters scope={scope} onScopeChange={setScope} />
        <ToggleGroup
          type="single"
          value={view}
          onValueChange={(v) => {
            if (v === 'board' || v === 'overdue' || v === 'soon') setView(v);
          }}
        >
          <ToggleGroupItem value="board">Board</ToggleGroupItem>
          <ToggleGroupItem value="overdue">Overdue</ToggleGroupItem>
          <ToggleGroupItem value="soon">Due soon</ToggleGroupItem>
        </ToggleGroup>
      </div>
      <PipelineKanbanBoard<TaskCard>
        mode="tasks"
        columnOrder={board.column_order}
        initialColumns={cols}
        getItemId={(item) => `${item.kind}-${item.id ?? item.title}`}
        columnTitle={colTitle}
        renderCard={(item) => (
          <div className="space-y-1">
            <div className="text-xs uppercase text-muted-foreground">{item.kind === 'crm' ? 'Task' : 'Activity'}</div>
            <div className="font-medium text-sm line-clamp-2">{item.title}</div>
            {item.due_on ? <div className="text-xs text-muted-foreground">Due {item.due_on}</div> : null}
            {item.tender_code ? (
              <div className="text-xs text-muted-foreground">
                {item.tender_code}
                {item.quotation_code ? ` / ${item.quotation_code}` : ''}
              </div>
            ) : null}
            {item.lead_code ? <div className="text-xs text-muted-foreground">Lead {item.lead_code}</div> : null}
          </div>
        )}
        onCrossColumnMove={async ({ item, toColumn }) => {
          if (item.kind !== 'crm' || !item.id) return;
          await patchPipelineTaskStatus(item.id, toColumn);
        }}
      />
    </div>
  );
}
