'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { ListBoardViewToggle } from '@/components/common/ListBoardViewToggle';
import { useListBoardViewPreference } from '@/hooks/useListBoardViewPreference';
import { Plus } from 'lucide-react';
import { getTickets } from '../services/ticketService';
import type {
  Ticket,
  TicketCategory,
  TicketListFilters,
  TicketPriority,
  TicketSourceChannel,
  TicketStatus,
} from '../types/ticket.types';
import {
  TICKET_CATEGORIES,
  TICKET_PRIORITIES,
  TICKET_SOURCE_CHANNELS,
  TICKET_STATUSES,
} from '../types/ticket.types';
import { TicketPriorityBadge, TicketStatusBadge } from './TicketStatusBadge';
import TicketsKanban from './TicketsKanban';

const PAGE_SIZE = 50;

export default function TicketsList() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { mode, setMode, hydrated } = useListBoardViewPreference('tickets', 'list');

  // URL ?view= overrides persisted choice if provided.
  const urlView = searchParams.get('view');
  useEffect(() => {
    if (!hydrated) return;
    if (urlView === 'list' || urlView === 'board') {
      if (urlView !== mode) setMode(urlView);
    }
  }, [urlView, hydrated, mode, setMode]);

  const [rows, setRows] = useState<Ticket[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<TicketStatus | 'all'>('all');
  const [priorityFilter, setPriorityFilter] = useState<TicketPriority | 'all'>('all');
  const [categoryFilter, setCategoryFilter] = useState<TicketCategory | 'all'>('all');
  const [sourceFilter, setSourceFilter] = useState<TicketSourceChannel | 'all'>('all');

  // Debounce search input.
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search.trim()), 300);
    return () => clearTimeout(t);
  }, [search]);

  // Reset to page 1 whenever filters change.
  useEffect(() => {
    setPage(1);
  }, [debouncedSearch, statusFilter, priorityFilter, categoryFilter, sourceFilter]);

  // Only fetch list-mode data when in list mode.
  useEffect(() => {
    if (mode !== 'list') return;
    let cancelled = false;
    setLoading(true);
    const filters: TicketListFilters & { page: number; limit: number } = {
      page,
      limit: PAGE_SIZE,
    };
    if (debouncedSearch) filters.q = debouncedSearch;
    if (statusFilter !== 'all') filters.status = statusFilter;
    if (priorityFilter !== 'all') filters.priority = priorityFilter;
    if (categoryFilter !== 'all') filters.category = categoryFilter;
    if (sourceFilter !== 'all') filters.source_channel = sourceFilter;
    getTickets(filters)
      .then((res) => {
        if (cancelled) return;
        setRows(res.data);
        setTotal(res.pagination.total);
      })
      .catch((e: Error) => {
        if (!cancelled) toast.error(e.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [mode, page, debouncedSearch, statusFilter, priorityFilter, categoryFilter, sourceFilter]);

  const totalPages = useMemo(
    () => Math.max(1, Math.ceil(total / PAGE_SIZE)),
    [total],
  );

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <Input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search title, description, ticket number…"
          className="max-w-sm"
        />
        {mode === 'list' && (
          <Select
            value={statusFilter}
            onValueChange={(v) => setStatusFilter(v as TicketStatus | 'all')}
          >
            <SelectTrigger className="w-[160px]">
              <SelectValue placeholder="Status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All statuses</SelectItem>
              {TICKET_STATUSES.map((s) => (
                <SelectItem key={s} value={s}>
                  {s.charAt(0).toUpperCase() + s.slice(1)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
        <Select
          value={priorityFilter}
          onValueChange={(v) => setPriorityFilter(v as TicketPriority | 'all')}
        >
          <SelectTrigger className="w-[160px]">
            <SelectValue placeholder="Priority" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All priorities</SelectItem>
            {TICKET_PRIORITIES.map((p) => (
              <SelectItem key={p} value={p}>
                {p.charAt(0).toUpperCase() + p.slice(1)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select
          value={categoryFilter}
          onValueChange={(v) => setCategoryFilter(v as TicketCategory | 'all')}
        >
          <SelectTrigger className="w-[160px]">
            <SelectValue placeholder="Category" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All categories</SelectItem>
            {TICKET_CATEGORIES.map((c) => (
              <SelectItem key={c} value={c}>
                {c.charAt(0).toUpperCase() + c.slice(1)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {mode === 'list' && (
          <Select
            value={sourceFilter}
            onValueChange={(v) => setSourceFilter(v as TicketSourceChannel | 'all')}
          >
            <SelectTrigger className="w-[180px]">
              <SelectValue placeholder="Source" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All sources</SelectItem>
              {TICKET_SOURCE_CHANNELS.map((s) => (
                <SelectItem key={s} value={s}>
                  {s === 'manual'
                    ? 'Manual'
                    : s === 'ai_assistant'
                    ? 'AI Assistant'
                    : 'WhatsApp'}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
        <ListBoardViewToggle value={mode} onChange={setMode} />
        <div className="ms-auto">
          <Button asChild>
            <Link href="/ticket-management/tickets/new">
              <Plus className="size-4" /> Create Ticket
            </Link>
          </Button>
        </div>
      </div>

      {mode === 'board' ? (
        <TicketsKanban
          filters={{
            q: debouncedSearch || undefined,
            priority: priorityFilter,
            category: categoryFilter,
          }}
        />
      ) : (
        <>
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[160px]">Ticket #</TableHead>
                  <TableHead>Title</TableHead>
                  <TableHead className="w-[120px]">Status</TableHead>
                  <TableHead className="w-[120px]">Priority</TableHead>
                  <TableHead className="w-[120px]">Category</TableHead>
                  <TableHead className="w-[120px]">Source</TableHead>
                  <TableHead className="w-[140px]">Due date</TableHead>
                  <TableHead className="w-[180px]">Assignee</TableHead>
                  <TableHead className="w-[160px]">Updated</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading ? (
                  Array.from({ length: 5 }).map((_, i) => (
                    <TableRow key={`skel-${i}`}>
                      {Array.from({ length: 9 }).map((__, j) => (
                        <TableCell key={j}>
                          <Skeleton className="h-4 w-full" />
                        </TableCell>
                      ))}
                    </TableRow>
                  ))
                ) : rows.length === 0 ? (
                  <TableRow>
                    <TableCell
                      colSpan={9}
                      className="h-24 text-center text-muted-foreground"
                    >
                      No tickets match these filters.
                    </TableCell>
                  </TableRow>
                ) : (
                  rows.map((t) => (
                    <TableRow
                      key={t.id}
                      className="cursor-pointer hover:bg-muted/30"
                      onClick={() => router.push(`/ticket-management/tickets/${t.id}`)}
                    >
                      <TableCell className="font-mono text-xs">
                        {t.ticket_number ?? '—'}
                      </TableCell>
                      <TableCell className="max-w-[420px] truncate">{t.title}</TableCell>
                      <TableCell>
                        <TicketStatusBadge status={t.status} />
                      </TableCell>
                      <TableCell>
                        <TicketPriorityBadge priority={t.priority} />
                      </TableCell>
                      <TableCell className="capitalize">{t.category}</TableCell>
                      <TableCell className="text-xs">
                        {t.source_channel === 'ai_assistant'
                          ? 'AI Assistant'
                          : t.source_channel === 'whatsapp_respond'
                          ? 'WhatsApp'
                          : 'Manual'}
                      </TableCell>
                      <TableCell className={t.is_overdue_resolution ? 'text-destructive' : ''}>
                        {t.due_date ?? '—'}
                      </TableCell>
                      <TableCell>
                        {t.assigned_to_user?.display_name ?? <span className="text-muted-foreground">Unassigned</span>}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {new Date(t.updated_at).toLocaleString()}
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>

          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">
              {total} total {total === 1 ? 'ticket' : 'tickets'}
            </span>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1 || loading}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                Previous
              </Button>
              <span className="text-sm">
                Page {page} of {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPages || loading}
                onClick={() => setPage((p) => p + 1)}
              >
                Next
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
