'use client';

import * as React from 'react';
import {
  Kanban,
  KanbanBoard,
  KanbanColumn,
  KanbanColumnContent,
  KanbanColumnHandle,
  KanbanItem,
  KanbanItemHandle,
  KanbanMoveEvent,
  KanbanOverlay,
} from '@/components/ui/kanban';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { GripVertical } from 'lucide-react';

export type PipelineBoardMode = 'leads' | 'tenders' | 'mq' | 'tasks' | 'projects';

export interface PipelineKanbanBoardProps<T extends Record<string, unknown>> {
  mode: PipelineBoardMode;
  columnOrder: string[];
  initialColumns: Record<string, T[]>;
  getItemId: (item: T) => string;
  renderCard: (item: T) => React.ReactNode;
  columnTitle: (columnId: string) => string;
  onCrossColumnMove?: (args: {
    item: T;
    fromColumn: string;
    toColumn: string;
  }) => Promise<void>;
}

export function PipelineKanbanBoard<T extends Record<string, unknown>>({
  columnOrder,
  initialColumns,
  getItemId,
  renderCard,
  columnTitle,
  onCrossColumnMove,
}: PipelineKanbanBoardProps<T>) {
  const [columns, setColumns] = React.useState<Record<string, T[]>>(() => {
    const next: Record<string, T[]> = {};
    for (const k of columnOrder) {
      next[k] = [...(initialColumns[k] ?? [])];
    }
    for (const k of Object.keys(initialColumns)) {
      if (!(k in next)) next[k] = [...initialColumns[k]];
    }
    return next;
  });

  React.useEffect(() => {
    const next: Record<string, T[]> = {};
    for (const k of columnOrder) {
      next[k] = [...(initialColumns[k] ?? [])];
    }
    for (const k of Object.keys(initialColumns)) {
      if (!(k in next)) next[k] = [...initialColumns[k]];
    }
    setColumns(next);
  }, [initialColumns, columnOrder]);

  const orderedColumns = React.useMemo(() => {
    const keys = [...columnOrder];
    for (const k of Object.keys(columns)) {
      if (!keys.includes(k)) keys.push(k);
    }
    return keys;
  }, [columnOrder, columns]);

  /** Keeps every column key in sync with props (avoids undefined when columnOrder grows before state updates). */
  const kanbanColumns = React.useMemo(() => {
    const next: Record<string, T[]> = { ...columns };
    for (const k of columnOrder) {
      if (!next[k]) next[k] = [...(initialColumns[k] ?? [])];
    }
    for (const k of Object.keys(initialColumns)) {
      if (!(k in next)) next[k] = [...initialColumns[k]];
    }
    return next;
  }, [columns, columnOrder, initialColumns]);

  const handleMove = React.useCallback(
    async (ev: KanbanMoveEvent) => {
      if (!onCrossColumnMove) return;
      const { activeContainer, overContainer, event } = ev;
      if (activeContainer === overContainer) return;
      const activeId = String(event.active.id);
      const fromList = columns[activeContainer] ?? [];
      const item = fromList.find((row) => getItemId(row) === activeId);
      if (!item) return;
      try {
        await onCrossColumnMove({ item, fromColumn: activeContainer, toColumn: overContainer });
        setColumns((prev) => {
          const src = [...(prev[activeContainer] ?? [])];
          const dst = [...(prev[overContainer] ?? [])];
          const idx = src.findIndex((row) => getItemId(row) === activeId);
          if (idx === -1) return prev;
          const [moved] = src.splice(idx, 1);
          dst.push(moved);
          return { ...prev, [activeContainer]: src, [overContainer]: dst };
        });
      } catch {
        // keep prior layout; parent may toast
      }
    },
    [columns, getItemId, onCrossColumnMove],
  );

  return (
    <Kanban value={kanbanColumns} onValueChange={setColumns} getItemValue={getItemId} onMove={onCrossColumnMove ? handleMove : undefined}>
      <KanbanBoard className="!grid !grid-cols-1 md:!grid-cols-2 xl:!grid-cols-3 2xl:!grid-cols-4 gap-4">
        {orderedColumns.map((col) => (
          <KanbanColumn key={col} value={col} className="min-h-[320px]">
            <Card className="h-full flex flex-col bg-muted/30">
              <CardHeader className="flex-row items-start justify-between gap-2 space-y-0 border-b border-border/50 py-3">
                <div className="min-w-0 flex-1 space-y-1">
                  <div className="text-sm font-semibold leading-tight text-foreground">{columnTitle(col)}</div>
                  <div className="text-xs text-muted-foreground">{(kanbanColumns[col] ?? []).length}</div>
                </div>
                {/* Handle alone: KanbanColumnHandle defaults to opacity-0 until hover — do not wrap the title */}
                <KanbanColumnHandle
                  className="!opacity-100 shrink-0 rounded-md p-1.5 text-muted-foreground hover:bg-muted/70 hover:text-foreground"
                  cursor
                >
                  <GripVertical className="size-4" aria-hidden />
                  <span className="sr-only">Reorder column</span>
                </KanbanColumnHandle>
              </CardHeader>
              <CardContent className="flex-1 pt-0">
                <KanbanColumnContent value={col} className="flex flex-col gap-2 min-h-[200px]">
                  {(kanbanColumns[col] ?? []).map((item) => (
                    <KanbanItem key={getItemId(item)} value={getItemId(item)}>
                      <KanbanItemHandle asChild>
                        <div
                          className={cn(
                            'rounded-md border bg-card p-3 shadow-sm cursor-grab active:cursor-grabbing',
                          )}
                        >
                          {renderCard(item)}
                        </div>
                      </KanbanItemHandle>
                    </KanbanItem>
                  ))}
                </KanbanColumnContent>
              </CardContent>
            </Card>
          </KanbanColumn>
        ))}
      </KanbanBoard>
      <KanbanOverlay>
        <div className="size-full rounded-md border bg-card/95 p-3 text-sm">Moving…</div>
      </KanbanOverlay>
    </Kanban>
  );
}
