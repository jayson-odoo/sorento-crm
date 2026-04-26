'use client';

import * as React from 'react';
import { PipelineKanbanBoard } from '../components/PipelineKanbanBoard';
import { PipelineScopeFilters } from '../components/PipelineScopeFilters';
import {
  fetchKanbanTenders,
  fetchStageConfig,
  patchTenderPipeline,
  type KanbanBoardPayload,
  type ScopeParam,
  type StageConfig,
} from '../services/commercialPipelineApi';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';

type TenderCard = {
  tender_code: string;
  title: string;
  pipeline_stage?: string | null;
  forecast_amount?: string | null;
  forecast_currency?: string | null;
  expected_close_on?: string | null;
  tender_outcome: string;
  owner_name?: string | null;
};

export function TendersKanbanClient() {
  const [scope, setScope] = React.useState<ScopeParam>('all');
  const [board, setBoard] = React.useState<KanbanBoardPayload | null>(null);
  const [stages, setStages] = React.useState<StageConfig | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    setError(null);
    try {
      const [cfg, b] = await Promise.all([fetchStageConfig(), fetchKanbanTenders(scope)]);
      setStages(cfg);
      setBoard(b);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load board');
    }
  }, [scope]);

  React.useEffect(() => {
    void load();
  }, [load]);

  const colTitle = React.useCallback(
    (code: string) => {
      if (code === '__none__') return 'Unassigned';
      const row = stages?.tender_stages.find((s) => s.code === code);
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

  const cols = board.columns as Record<string, TenderCard[]>;

  return (
    <div className="space-y-4">
      <PipelineScopeFilters scope={scope} onScopeChange={setScope} />
      <PipelineKanbanBoard<TenderCard>
        mode="tenders"
        columnOrder={board.column_order}
        initialColumns={cols}
        getItemId={(item) => item.tender_code}
        columnTitle={colTitle}
        renderCard={(item) => (
          <div className="space-y-1">
            <div className="font-medium text-sm">{item.tender_code}</div>
            <div className="text-sm text-muted-foreground line-clamp-2">{item.title}</div>
            {item.forecast_amount ? (
              <div className="text-xs text-muted-foreground">
                {item.forecast_amount} {item.forecast_currency ?? ''}
              </div>
            ) : null}
            {item.expected_close_on ? (
              <div className="text-xs text-muted-foreground">Close {item.expected_close_on}</div>
            ) : null}
            {item.owner_name ? <div className="text-xs text-muted-foreground">{item.owner_name}</div> : null}
          </div>
        )}
        onCrossColumnMove={async ({ item, toColumn }) => {
          const next = toColumn === '__none__' ? null : toColumn;
          await patchTenderPipeline(item.tender_code, next);
        }}
      />
    </div>
  );
}
