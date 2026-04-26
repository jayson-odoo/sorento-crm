'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { PipelineKanbanBoard } from '@/app/(protected)/commercial-management/pipeline/components/PipelineKanbanBoard';
import { getCommercialProjectsAllPages, updateCommercialProject } from '../services/commercialProjectService';
import type { CommercialProjectListRow } from '../types/commercialProject.types';
import { getWorkflowStages } from '@/app/(protected)/commercial-core/process-configuration/services/workflowStageService';

type ProjectCard = CommercialProjectListRow & Record<string, unknown>;

export function ProjectsKanbanClient({
  searchQuery,
  ownerUserId,
}: {
  searchQuery: string;
  ownerUserId: string | undefined;
}) {
  const router = useRouter();

  const { data: stages = [] } = useQuery({
    queryKey: ['workflow-stages', 'project'],
    queryFn: () => getWorkflowStages({ domain: 'project' }),
    staleTime: 60_000,
  });

  const { data: projectsResp, isPending } = useQuery({
    queryKey: ['commercial-projects-kanban', searchQuery, ownerUserId],
    queryFn: () =>
      getCommercialProjectsAllPages({
        sorting: [{ id: 'created_at', desc: true }],
        searchQuery,
        owner_user_id: ownerUserId,
      }),
    staleTime: 15_000,
  });

  const columnOrder = React.useMemo(() => {
    const ordered = [...stages].sort((a, b) => a.sort_order - b.sort_order).map((s) => s.id);
    return [...ordered, '__none__'];
  }, [stages]);

  const initialColumns = React.useMemo(() => {
    const rows = projectsResp?.data ?? [];
    const cols: Record<string, ProjectCard[]> = {};
    for (const id of columnOrder) cols[id] = [];
    for (const p of rows) {
      const key = p.project_stage_id || '__none__';
      if (!cols[key]) cols[key] = [];
      cols[key].push(p as ProjectCard);
    }
    return cols;
  }, [projectsResp?.data, columnOrder]);

  const columnTitle = React.useCallback(
    (id: string) => {
      if (id === '__none__') return 'Unassigned';
      return stages.find((s) => s.id === id)?.label ?? id;
    },
    [stages],
  );

  if (isPending && !projectsResp) {
    return <div className="text-muted-foreground min-h-[320px] rounded-lg border bg-muted/20 p-8 text-sm">Loading board…</div>;
  }

  return (
    <PipelineKanbanBoard<ProjectCard>
      mode="projects"
      columnOrder={columnOrder}
      initialColumns={initialColumns}
      getItemId={(item) => item.id}
      columnTitle={columnTitle}
      renderCard={(item) => (
        <div
          role="link"
          tabIndex={0}
          className="w-full cursor-pointer space-y-1 text-left"
          onClick={() => router.push(`/commercial-management/projects/${item.id}`)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              router.push(`/commercial-management/projects/${item.id}`);
            }
          }}
        >
          <div className="font-medium text-sm">{item.title}</div>
          {item.customer_name ? <div className="text-muted-foreground text-xs">{item.customer_name}</div> : null}
        </div>
      )}
      onCrossColumnMove={async ({ item, toColumn }) => {
        if (toColumn === '__none__') return;
        try {
          await updateCommercialProject(item.id, { project_stage_id: toColumn });
        } catch (e) {
          toast.error(e instanceof Error ? e.message : 'Could not update project stage');
          throw e;
        }
      }}
    />
  );
}
