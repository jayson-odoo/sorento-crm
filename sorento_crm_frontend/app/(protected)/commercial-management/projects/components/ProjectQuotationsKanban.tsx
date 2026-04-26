'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { PipelineKanbanBoard } from '@/app/(protected)/commercial-management/pipeline/components/PipelineKanbanBoard';
import { fetchStageConfig, patchMqExecution, type StageConfig } from '@/app/(protected)/commercial-management/pipeline/services/commercialPipelineApi';
import type { CommercialProjectMasterQuotationRow } from '../types/commercialProject.types';
import { masterQuotationDisplayCode } from '@/app/(protected)/commercial-management/quotations/lib/masterQuotationDisplayCode';

type CardRow = CommercialProjectMasterQuotationRow & Record<string, unknown>;

function buildColumnOrder(mqStages: StageConfig['mq_execution_states'], quotations: CommercialProjectMasterQuotationRow[]) {
  const base = [...mqStages].sort((a, b) => a.sort_order - b.sort_order).map((s) => s.code);
  const seen = new Set(base);
  for (const q of quotations) {
    const c = q.quotation_stage?.stage_code;
    if (c && !seen.has(c)) {
      base.push(c);
      seen.add(c);
    }
  }
  return [...base, '__none__'];
}

export function ProjectQuotationsKanban({
  quotations,
  workspaceHref,
  onMoved,
}: {
  quotations: CommercialProjectMasterQuotationRow[];
  workspaceHref: (q: CommercialProjectMasterQuotationRow) => string;
  onMoved: () => void;
}) {
  const router = useRouter();
  const { data: stagesCfg } = useQuery({
    queryKey: ['pipeline-stage-config'],
    queryFn: fetchStageConfig,
    staleTime: 60_000,
  });

  const mqStages = React.useMemo(() => stagesCfg?.mq_execution_states ?? [], [stagesCfg]);

  const columnOrder = React.useMemo(() => buildColumnOrder(mqStages, quotations), [mqStages, quotations]);

  const initialColumns = React.useMemo(() => {
    const cols: Record<string, CardRow[]> = {};
    for (const k of columnOrder) cols[k] = [];
    for (const q of quotations) {
      const code = q.quotation_stage?.stage_code;
      const key =
        code && columnOrder.includes(code) ? code : '__none__';
      if (!cols[key]) cols[key] = [];
      cols[key].push(q as CardRow);
    }
    return cols;
  }, [quotations, columnOrder]);

  const columnTitle = React.useCallback(
    (code: string) => {
      if (code === '__none__') return 'Unassigned';
      return mqStages.find((s) => s.code === code)?.label ?? code;
    },
    [mqStages],
  );

  return (
    <PipelineKanbanBoard<CardRow>
      mode="mq"
      columnOrder={columnOrder}
      initialColumns={initialColumns}
      getItemId={(item) => `${item.tender_code}::${item.quotation_code}`}
      columnTitle={columnTitle}
      renderCard={(item) => {
        const href = workspaceHref(item);
        return (
          <div
            role="link"
            tabIndex={0}
            className="w-full cursor-pointer space-y-1 text-left"
            onClick={() => router.push(href)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                router.push(href);
              }
            }}
          >
            <div className="font-medium text-sm">
              {item.tender_code} / {masterQuotationDisplayCode(item)}
            </div>
            <div className="text-muted-foreground line-clamp-2 text-sm">{item.title}</div>
            <div className="text-muted-foreground text-xs">Path: {item.path_role}</div>
            {item.owner_name ? (
              <div className="text-muted-foreground text-xs">Sales: {item.owner_name}</div>
            ) : null}
          </div>
        );
      }}
      onCrossColumnMove={async ({ item, toColumn }) => {
        if (toColumn === '__none__') return;
        try {
          const r = await patchMqExecution(item.tender_code, item.quotation_code, toColumn);
          if (r.rerouted_for_approval) {
            toast.info('Pricing approval required', {
              description: `Quotation was moved to stage “${r.applied_stage_code ?? toColumn}” pending approval.`,
            });
          }
          onMoved();
        } catch (e) {
          toast.error(e instanceof Error ? e.message : 'Could not update quotation stage');
          throw e;
        }
      }}
    />
  );
}
