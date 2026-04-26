'use client';

import * as React from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Skeleton } from '@/components/ui/skeleton';
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type { ListQueryFilterGroup } from '@/lib/list-query/listQueryService';
import { PipelineKanbanBoard } from '../../pipeline/components/PipelineKanbanBoard';

type KanbanItem = {
  id: string;
  project_id: string;
  title: string;
  status_code: string | null;
  assignee_user_id?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  project_title?: string | null;
  lead_code?: string | null;
  customer_name?: string | null;
  developer_name?: string | null;
};

type KanbanColumn = {
  status_id: string;
  status_code: string;
  status_label: string;
  sort_order: number;
  items: KanbanItem[];
};

type KanbanResponse = { columns: KanbanColumn[] };

export function ProjectTasksKanban({
  searchQuery,
  assigneeUserId,
  advancedFilter,
}: {
  searchQuery: string;
  assigneeUserId: string | null;
  advancedFilter: ListQueryFilterGroup | null;
}) {
  const queryClient = useQueryClient();

  const { data, isLoading, error, refetch } = useQuery<KanbanResponse>({
    queryKey: ['commercial-project-tasks-kanban', searchQuery, assigneeUserId, advancedFilter],
    queryFn: async () => {
      const r = await apiFetch('/api/v1/commercial/projects/tasks/kanban', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          quick_search: searchQuery || undefined,
          assignee_user_id: assigneeUserId || undefined,
        }),
      });
      if (!r.ok) throw new Error(await extractApiError(r, 'Failed to load kanban'));
      return r.json();
    },
  });

  const columnOrder = React.useMemo(() => {
    if (!data) return [] as string[];
    return [...data.columns]
      .sort((a, b) => a.sort_order - b.sort_order)
      .map((c) => c.status_code);
  }, [data]);

  const initialColumns = React.useMemo(() => {
    const out: Record<string, KanbanItem[]> = {};
    if (!data) return out;
    for (const c of data.columns) out[c.status_code] = c.items;
    return out;
  }, [data]);

  const labelByCode = React.useMemo(() => {
    const m = new Map<string, string>();
    if (!data) return m;
    for (const c of data.columns) m.set(c.status_code, c.status_label);
    return m;
  }, [data]);

  if (isLoading) return <Skeleton className="h-80 w-full" />;
  if (error) {
    return (
      <Alert variant="destructive">
        <AlertTitle>Error</AlertTitle>
        <AlertDescription>{error instanceof Error ? error.message : 'Failed to load board'}</AlertDescription>
      </Alert>
    );
  }
  if (!data) return null;

  return (
    <PipelineKanbanBoard<KanbanItem>
      mode="tasks"
      columnOrder={columnOrder}
      initialColumns={initialColumns}
      getItemId={(item) => item.id}
      columnTitle={(code) => labelByCode.get(code) ?? code}
      renderCard={(item) => (
        <div className="space-y-1">
          <div className="text-xs uppercase text-muted-foreground">Project task</div>
          <div className="font-medium text-sm line-clamp-2">{item.title}</div>
          {item.project_title ? (
            <div className="text-xs text-muted-foreground line-clamp-1">{item.project_title}</div>
          ) : null}
          {item.end_date ? (
            <div className="text-xs text-muted-foreground">End {item.end_date.slice(0, 10)}</div>
          ) : null}
          {item.developer_name ? (
            <div className="text-xs text-muted-foreground line-clamp-1">{item.developer_name}</div>
          ) : null}
        </div>
      )}
      onCrossColumnMove={async ({ item, toColumn }) => {
        const r = await apiFetch(`/api/v1/commercial/projects/tasks/${item.id}/status`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ status_code: toColumn }),
        });
        if (!r.ok) {
          toast.error(await extractApiError(r, 'Failed to update status'));
          throw new Error('status update failed');
        }
        await queryClient.invalidateQueries({ queryKey: ['commercial-project-tasks-kanban'] });
        await refetch();
      }}
    />
  );
}
