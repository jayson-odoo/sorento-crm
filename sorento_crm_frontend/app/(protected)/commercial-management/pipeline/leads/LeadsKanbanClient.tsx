'use client';

import * as React from 'react';
import { PipelineKanbanBoard } from '../components/PipelineKanbanBoard';
import { PipelineScopeFilters } from '../components/PipelineScopeFilters';
import {
  fetchKanbanLeads,
  fetchStageConfig,
  patchLeadStage,
  type KanbanBoardPayload,
  type ScopeParam,
  type StageConfig,
} from '../services/commercialPipelineApi';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';

type LeadCard = {
  lead_code: string;
  title: string;
  stage_code: string;
  owner_name?: string | null;
};

export function LeadsKanbanClient() {
  const [scope, setScope] = React.useState<ScopeParam>('all');
  const [board, setBoard] = React.useState<KanbanBoardPayload | null>(null);
  const [stages, setStages] = React.useState<StageConfig | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    setError(null);
    try {
      const [cfg, b] = await Promise.all([fetchStageConfig(), fetchKanbanLeads(scope)]);
      setStages(cfg);
      setBoard(b);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load board');
    }
  }, [scope]);

  React.useEffect(() => {
    void load();
  }, [load]);

  const stageLabel = React.useCallback(
    (code: string) => {
      if (code === '__none__') return 'Unassigned';
      const row = stages?.lead_stages.find((s) => s.code === code);
      return row?.label ?? code;
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

  const cols = board.columns as Record<string, LeadCard[]>;

  return (
    <div className="space-y-4">
      <PipelineScopeFilters scope={scope} onScopeChange={setScope} />
      <PipelineKanbanBoard<LeadCard>
        mode="leads"
        columnOrder={board.column_order}
        initialColumns={cols}
        getItemId={(item) => item.lead_code}
        columnTitle={stageLabel}
        renderCard={(item) => (
          <div className="space-y-1">
            <div className="font-medium text-sm">{item.lead_code}</div>
            <div className="text-sm text-muted-foreground line-clamp-2">{item.title}</div>
            {item.owner_name ? <div className="text-xs text-muted-foreground">{item.owner_name}</div> : null}
          </div>
        )}
        onCrossColumnMove={async ({ item, toColumn }) => {
          await patchLeadStage(item.lead_code, toColumn);
        }}
      />
    </div>
  );
}
