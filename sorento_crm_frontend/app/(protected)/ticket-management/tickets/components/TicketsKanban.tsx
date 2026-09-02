'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { toast } from '@/lib/toast';
import {
  Kanban,
  KanbanBoard,
  KanbanColumn,
  KanbanColumnContent,
  KanbanItem,
  type KanbanMoveEvent,
} from '@/components/ui/kanban';
import { Skeleton } from '@/components/ui/skeleton';
import { changeTicketStatus, getTicketsKanban } from '../services/ticketService';
import {
  TICKET_STATUSES,
  type Ticket,
  type TicketCategory,
  type TicketListFilters,
  type TicketPriority,
  type TicketStatus,
} from '../types/ticket.types';
import { TicketPriorityBadge } from './TicketStatusBadge';

const COLUMN_LABELS: Record<TicketStatus, string> = {
  draft: 'Draft',
  submitted: 'Submitted',
  assigned: 'Assigned',
  responded: 'Responded',
  resolved: 'Resolved',
};

function emptyColumns(): Record<TicketStatus, Ticket[]> {
  return {
    draft: [],
    submitted: [],
    assigned: [],
    responded: [],
    resolved: [],
  };
}

interface Props {
  filters: {
    q?: string;
    priority?: TicketPriority | 'all';
    category?: TicketCategory | 'all';
  };
}

export default function TicketsKanban({ filters }: Props) {
  const router = useRouter();
  const [columns, setColumns] = useState<Record<TicketStatus, Ticket[]>>(emptyColumns());
  const [counts, setCounts] = useState<Record<TicketStatus, number>>(
    Object.fromEntries(TICKET_STATUSES.map((s) => [s, 0])) as Record<TicketStatus, number>,
  );
  const [loading, setLoading] = useState(true);
  const [savingId, setSavingId] = useState<string | null>(null);

  async function reload() {
    setLoading(true);
    try {
      const apiFilters: TicketListFilters = {};
      if (filters.q) apiFilters.q = filters.q;
      if (filters.priority && filters.priority !== 'all') apiFilters.priority = filters.priority;
      if (filters.category && filters.category !== 'all') apiFilters.category = filters.category;
      const res = await getTicketsKanban(apiFilters);
      setColumns({
        draft: res.columns.draft ?? [],
        submitted: res.columns.submitted ?? [],
        assigned: res.columns.assigned ?? [],
        responded: res.columns.responded ?? [],
        resolved: res.columns.resolved ?? [],
      });
      setCounts({
        draft: res.counts.draft ?? 0,
        submitted: res.counts.submitted ?? 0,
        assigned: res.counts.assigned ?? 0,
        responded: res.counts.responded ?? 0,
        resolved: res.counts.resolved ?? 0,
      });
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void reload();
     
  }, [filters.q, filters.priority, filters.category]);

  async function handleMove(ev: KanbanMoveEvent) {
    const { activeContainer, overContainer } = ev;
    if (activeContainer === overContainer) return;
    if (!TICKET_STATUSES.includes(activeContainer as TicketStatus)) return;
    if (!TICKET_STATUSES.includes(overContainer as TicketStatus)) return;
    const ticketId = String(ev.event.active.id);
    const newStatus = overContainer as TicketStatus;
    setSavingId(ticketId);
    try {
      const updated = await changeTicketStatus(ticketId, { new_status: newStatus });
      // Replace the moved card in-place with the server-returned ticket so SLA fields refresh.
      setColumns((prev) => {
        const next = { ...prev };
        for (const k of TICKET_STATUSES) {
          next[k] = next[k].map((t) => (t.id === ticketId ? updated : t));
        }
        return next;
      });
    } catch (e) {
      toast.error((e as Error).message);
      // Roll back by reloading the board state from server.
      void reload();
    } finally {
      setSavingId(null);
    }
  }

  if (loading) {
    return (
      <div className="grid grid-cols-5 gap-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-64 w-full" />
        ))}
      </div>
    );
  }

  return (
    <Kanban
      value={columns}
      onValueChange={(v) => setColumns(v as Record<TicketStatus, Ticket[]>)}
      getItemValue={(t: Ticket) => t.id}
      onMove={handleMove}
    >
      <KanbanBoard className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-3">
        {TICKET_STATUSES.map((status) => (
          <KanbanColumn
            key={status}
            value={status}
            className="flex flex-col gap-2 rounded-md border bg-muted/20 p-3 min-h-[300px]"
          >
            <div className="flex items-center justify-between mb-1">
              <h3 className="text-sm font-semibold">{COLUMN_LABELS[status]}</h3>
              <span className="text-xs text-muted-foreground">
                {columns[status].length}
                {counts[status] > columns[status].length
                  ? ` of ${counts[status]}`
                  : ''}
              </span>
            </div>
            <KanbanColumnContent value={status} className="flex flex-col gap-2 min-h-[40px]">
              {columns[status].length === 0 ? (
                <p className="text-xs text-muted-foreground italic px-1">Drop a card here</p>
              ) : (
                columns[status].map((t) => (
                  <KanbanItem key={t.id} value={t.id} asChild>
                    <div
                      className={`rounded-md border bg-background p-3 cursor-pointer hover:shadow-sm ${
                        savingId === t.id ? 'opacity-50' : ''
                      }`}
                      onClick={(e) => {
                        // Avoid swallowing the drag listener.
                        if (savingId === t.id) return;
                        e.stopPropagation();
                        router.push(`/ticket-management/tickets/${t.id}`);
                      }}
                    >
                      <div className="flex items-center gap-2 mb-1">
                        <span className="whitespace-nowrap font-mono text-[10px] text-muted-foreground">
                          {t.ticket_number ?? '-'}
                        </span>
                        <span className="ms-auto">
                          <TicketPriorityBadge priority={t.priority} />
                        </span>
                      </div>
                      <p className="text-sm font-medium line-clamp-2">{t.title}</p>
                      <div className="flex items-center gap-2 text-xs text-muted-foreground mt-2">
                        <span className="truncate">
                          {t.assigned_to_user?.display_name ?? 'Unassigned'}
                        </span>
                        {t.due_date && (
                          <span
                            className={`ms-auto ${t.is_overdue_resolution ? 'text-destructive' : ''}`}
                          >
                            {t.due_date}
                          </span>
                        )}
                      </div>
                    </div>
                  </KanbanItem>
                ))
              )}
            </KanbanColumnContent>
          </KanbanColumn>
        ))}
      </KanbanBoard>
    </Kanban>
  );
}
