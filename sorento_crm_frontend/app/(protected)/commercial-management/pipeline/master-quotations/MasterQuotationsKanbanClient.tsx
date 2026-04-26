'use client';

import * as React from 'react';
import { PipelineKanbanBoard } from '../components/PipelineKanbanBoard';
import { PipelineScopeFilters } from '../components/PipelineScopeFilters';
import {
  fetchKanbanMasterQuotations,
  fetchStageConfig,
  patchMqExecution,
  type KanbanBoardPayload,
  type ScopeParam,
  type StageConfig,
} from '../services/commercialPipelineApi';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { toast } from 'sonner';
import { masterQuotationDisplayCode } from '@/app/(protected)/commercial-management/quotations/lib/masterQuotationDisplayCode';

type MqCard = {
  tender_code: string;
  quotation_code: string;
  current_working_revision_number?: number | null;
  title: string;
  execution_state: string;
  path_role: string;
  salesperson_name?: string | null;
} & Record<string, unknown>;

export function MasterQuotationsKanbanClient() {
  const [scope, setScope] = React.useState<ScopeParam>('all');
  const [board, setBoard] = React.useState<KanbanBoardPayload | null>(null);
  const [stages, setStages] = React.useState<StageConfig | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    setError(null);
    try {
      const [cfg, b] = await Promise.all([fetchStageConfig(), fetchKanbanMasterQuotations(scope)]);
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
      const row = stages?.mq_execution_states.find((s) => s.code === code);
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

  const cols = board.columns as Record<string, MqCard[]>;

  return (
    <div className="space-y-4">
      <PipelineScopeFilters scope={scope} onScopeChange={setScope} />
      <PipelineKanbanBoard<MqCard>
        mode="mq"
        columnOrder={board.column_order}
        initialColumns={cols}
        getItemId={(item) => `${item.tender_code}::${item.quotation_code}`}
        columnTitle={colTitle}
        renderCard={(item) => (
          <div className="space-y-1">
            <div className="font-medium text-sm">
              {item.tender_code} / {masterQuotationDisplayCode(item)}
            </div>
            <div className="text-sm text-muted-foreground line-clamp-2">{item.title}</div>
            <div className="text-xs font-medium text-foreground">
              {colTitle((item.execution_state as string)?.trim() ? String(item.execution_state) : '__none__')}
            </div>
            <div className="text-xs text-muted-foreground">Path: {item.path_role}</div>
            {item.salesperson_name ? (
              <div className="text-xs text-muted-foreground">Sales: {item.salesperson_name}</div>
            ) : null}
          </div>
        )}
        onCrossColumnMove={async ({ item, toColumn }) => {
          try {
            if (toColumn === '__none__') return;
            const r = await patchMqExecution(item.tender_code, item.quotation_code, toColumn);
            if (r.rerouted_for_approval) {
              toast.info('Pricing approval required', {
                description: `Quotation was moved to stage “${r.applied_stage_code ?? toColumn}” pending approval.`,
              });
            }
            await load();
          } catch (e) {
            toast.error(e instanceof Error ? e.message : 'Failed to update quotation stage');
            throw e;
          }
        }}
      />
    </div>
  );
}
