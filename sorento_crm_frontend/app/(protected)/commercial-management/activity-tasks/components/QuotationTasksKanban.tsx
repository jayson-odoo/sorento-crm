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
  master_quotation_id: string;
  title: string;
  status_code: string | null;
  assignee_user_id?: string | null;
  due_at?: string | null;
  is_tender_level?: boolean;
  quotation_code?: string | null;
  tender_code?: string | null;
};

type KanbanColumn = {
  status_id: string;
  status_code: string;
  status_label: string;
  sort_order: number;
  items: KanbanItem[];
};

type KanbanResponse = { columns: KanbanColumn[] };

export function QuotationTasksKanban({
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
    queryKey: ['commercial-activity-tasks-kanban', searchQuery, assigneeUserId, advancedFilter],
    queryFn: async () => {
      const r = await apiFetch('/api/v1/commercial-activity/activity-tasks/kanban', {
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
          <div className="text-xs uppercase text-muted-foreground">Quotation task</div>
          <div className="font-medium text-sm line-clamp-2">{item.title}</div>
          {item.quotation_code ? (
            <div className="text-xs text-muted-foreground line-clamp-1">
              {item.quotation_code}
              {item.tender_code ? ` / ${item.tender_code}` : ''}
            </div>
          ) : null}
          {item.due_at ? (
            <div className="text-xs text-muted-foreground">Due {item.due_at.slice(0, 10)}</div>
          ) : null}
        </div>
      )}
      onCrossColumnMove={async ({ item, toColumn }) => {
        const r = await apiFetch(`/api/v1/commercial-activity/activity-tasks/${item.id}/status`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ status_code: toColumn }),
        });
        if (!r.ok) {
          toast.error(await extractApiError(r, 'Failed to update status'));
          throw new Error('status update failed');
        }
        await queryClient.invalidateQueries({ queryKey: ['commercial-activity-tasks-kanban'] });
        await refetch();
      }}
    />
  );
}
