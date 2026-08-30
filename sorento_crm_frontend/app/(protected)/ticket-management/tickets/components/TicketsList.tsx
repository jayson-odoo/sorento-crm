'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { SearchableSelect } from '@/components/common/SearchableSelect';
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
import { Plus, Trash2 } from 'lucide-react';
import { Checkbox } from '@/components/ui/checkbox';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { bulkDeleteTickets, getTickets } from '../services/ticketService';
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
  const {
    value: search,
    setValue: setSearch,
    debouncedValue: debouncedSearch,
    isSettling: debouncedSearchSettling,
  } = useDebouncedSearch();
  const [statusFilter, setStatusFilter] = useState<TicketStatus | 'all'>('all');
  const [priorityFilter, setPriorityFilter] = useState<TicketPriority | 'all'>('all');
  const [categoryFilter, setCategoryFilter] = useState<TicketCategory | 'all'>('all');
  const [sourceFilter, setSourceFilter] = useState<TicketSourceChannel | 'all'>('all');
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false);
  const [reloadTick, setReloadTick] = useState(0);

  // Reset to page 1 whenever filters change.
  useEffect(() => {
    setPage(1);
  }, [debouncedSearch, statusFilter, priorityFilter, categoryFilter, sourceFilter]);

  // Clear selection on filter / page change.
  useEffect(() => {
    setSelected(new Set());
  }, [page, debouncedSearch, statusFilter, priorityFilter, categoryFilter, sourceFilter, mode]);

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
  }, [mode, page, debouncedSearch, statusFilter, priorityFilter, categoryFilter, sourceFilter, reloadTick]);

  const allSelectedOnPage = rows.length > 0 && rows.every((r) => selected.has(r.id));
  const someSelectedOnPage = rows.some((r) => selected.has(r.id));

  function toggleAllOnPage(checked: boolean) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (checked) rows.forEach((r) => next.add(r.id));
      else rows.forEach((r) => next.delete(r.id));
      return next;
    });
  }

  function toggleRow(id: string, checked: boolean) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (checked) next.add(id);
      else next.delete(id);
      return next;
    });
  }

  const totalPages = useMemo(
    () => Math.max(1, Math.ceil(total / PAGE_SIZE)),
    [total],
  );

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <ListSearchInput
          value={search}
          onChange={setSearch}
          isSettling={debouncedSearchSettling}
          placeholder="Search title, description, ticket number…"
          aria-label="Search tickets"
          className="max-w-sm"
        />
        {mode === 'list' && (
          <SearchableSelect
            value={statusFilter}
            onChange={(v) => setStatusFilter(v as TicketStatus | 'all')}
            options={[
              { value: 'all', label: 'All statuses' },
              ...TICKET_STATUSES.map((s) => ({
                value: s,
                label: s.charAt(0).toUpperCase() + s.slice(1),
              })),
            ]}
            placeholder="Status"
            triggerClassName="w-[160px]"
          />
        )}
        <SearchableSelect
          value={priorityFilter}
          onChange={(v) => setPriorityFilter(v as TicketPriority | 'all')}
          options={[
            { value: 'all', label: 'All priorities' },
            ...TICKET_PRIORITIES.map((p) => ({
              value: p,
              label: p.charAt(0).toUpperCase() + p.slice(1),
            })),
          ]}
          placeholder="Priority"
          triggerClassName="w-[160px]"
        />
        <SearchableSelect
          value={categoryFilter}
          onChange={(v) => setCategoryFilter(v as TicketCategory | 'all')}
          options={[
            { value: 'all', label: 'All categories' },
            ...TICKET_CATEGORIES.map((c) => ({
              value: c,
              label: c.charAt(0).toUpperCase() + c.slice(1),
            })),
          ]}
          placeholder="Category"
          triggerClassName="w-[160px]"
        />
        {mode === 'list' && (
          <SearchableSelect
            value={sourceFilter}
            onChange={(v) => setSourceFilter(v as TicketSourceChannel | 'all')}
            options={[
              { value: 'all', label: 'All sources' },
              ...TICKET_SOURCE_CHANNELS.map((s) => ({
                value: s,
                label:
                  s === 'manual' ? 'Manual' : s === 'ai_assistant' ? 'AI Assistant' : 'WhatsApp',
              })),
            ]}
            placeholder="Source"
            triggerClassName="w-[180px]"
          />
        )}
        <ListBoardViewToggle value={mode} onChange={setMode} />
        <div className="ms-auto flex items-center gap-2">
          {mode === 'list' && selected.size > 0 && (
            <Button
              variant="destructive"
              onClick={() => setBulkDeleteOpen(true)}
            >
              <Trash2 className="size-4" />
              Delete {selected.size} selected
            </Button>
          )}
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
                  <TableHead className="w-[40px]">
                    <Checkbox
                      checked={
                        allSelectedOnPage
                          ? true
                          : someSelectedOnPage
                          ? 'indeterminate'
                          : false
                      }
                      onCheckedChange={(v) => toggleAllOnPage(v === true)}
                      aria-label="Select all rows on this page"
                    />
                  </TableHead>
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
                      {Array.from({ length: 10 }).map((__, j) => (
                        <TableCell key={j}>
                          <Skeleton className="h-4 w-full" />
                        </TableCell>
                      ))}
                    </TableRow>
                  ))
                ) : rows.length === 0 ? (
                  <TableRow>
                    <TableCell
                      colSpan={10}
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
                      <TableCell onClick={(e) => e.stopPropagation()}>
                        <Checkbox
                          checked={selected.has(t.id)}
                          onCheckedChange={(v) => toggleRow(t.id, v === true)}
                          aria-label={`Select ticket ${t.ticket_number ?? t.id}`}
                        />
                      </TableCell>
                      <TableCell className="whitespace-nowrap font-mono text-xs">
                        {t.ticket_number ?? '-'}
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
                        {t.due_date ?? '-'}
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

      <ConfirmDeleteDialog
        open={bulkDeleteOpen}
        onOpenChange={setBulkDeleteOpen}
        description={
          <>
            Permanently delete <strong>{selected.size}</strong>{' '}
            {selected.size === 1 ? 'ticket' : 'tickets'}? This action cannot be undone.
          </>
        }
        onDelete={async () => {
          await bulkDeleteTickets(Array.from(selected));
        }}
        successMessage={`${selected.size} ${selected.size === 1 ? 'ticket' : 'tickets'} deleted`}
        onSuccess={() => {
          setSelected(new Set());
          setReloadTick((n) => n + 1);
        }}
      />
    </div>
  );
}
