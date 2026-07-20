'use client';

import { useMemo, useState } from 'react';
import { Download, MessageSquare, Search } from 'lucide-react';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Container } from '@/components/common/container';
import {
  Toolbar,
  ToolbarActions,
  ToolbarHeading,
  ToolbarTitle,
} from '@/components/common/toolbar';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { useChatMessages, useExportChatHistory } from './hooks/useChatHistory';
import { ChatThreadDrawer } from './components/ChatThreadDrawer';
import type { ChatHistoryFilters, ChatMessageRow } from './types/chatHistory.types';

/** `datetime-local` value for "now minus N hours", in the browser's own zone. */
function localInput(offsetHours: number): string {
  const d = new Date(Date.now() - offsetHours * 3600_000);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

const DIRECTION_OPTIONS = [
  { value: '', label: 'All directions' },
  { value: 'incoming', label: 'Incoming' },
  { value: 'outgoing', label: 'Outgoing' },
];

function LatencyCell({ seconds }: { seconds: number | null }) {
  if (seconds == null) return <span className="text-muted-foreground">—</span>;
  const variant = seconds > 30 ? 'destructive' : seconds > 10 ? 'warning' : 'success';
  return (
    <Badge variant={variant as never}>
      {seconds < 1 ? `${Math.round(seconds * 1000)}ms` : `${seconds.toFixed(1)}s`}
    </Badge>
  );
}

export default function ChatHistoryPage() {
  // Default to the last 24h — an unbounded scan of this table is never the intent.
  const [dateFrom, setDateFrom] = useState(() => localInput(24));
  const [dateTo, setDateTo] = useState(() => localInput(0));
  const [search, setSearch] = useState('');
  const [direction, setDirection] = useState('');
  const [breachedOnly, setBreachedOnly] = useState(false);

  // Cursor stack, so "Previous" is a pop rather than a re-query from the top.
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const [pageIndex, setPageIndex] = useState(0);
  const [selected, setSelected] = useState<ChatMessageRow | null>(null);

  const filters: ChatHistoryFilters = useMemo(
    () => ({
      date_from: dateFrom ? new Date(dateFrom).toISOString() : undefined,
      date_to: dateTo ? new Date(dateTo).toISOString() : undefined,
      search: search.trim() || undefined,
      direction: (direction || undefined) as ChatHistoryFilters['direction'],
      breached_only: breachedOnly || undefined,
    }),
    [dateFrom, dateTo, search, direction, breachedOnly],
  );

  const { data, isLoading, isFetching } = useChatMessages(filters, {
    cursor: cursors[pageIndex],
    limit: 50,
  });
  const exportMutation = useExportChatHistory();

  const resetPaging = () => {
    setCursors([null]);
    setPageIndex(0);
  };

  const goNext = () => {
    if (!data?.next_cursor) return;
    setCursors((prev) => {
      const next = prev.slice(0, pageIndex + 1);
      next.push(data.next_cursor);
      return next;
    });
    setPageIndex((i) => i + 1);
  };

  const rows = data?.data ?? [];

  return (
    <>
      <Container>
        <Toolbar>
          <ToolbarHeading>
            <ToolbarTitle>Chat History</ToolbarTitle>
            <Breadcrumb>
              <BreadcrumbList>
                <BreadcrumbItem>
                  <BreadcrumbLink href="/">Home</BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbPage>System Management</BreadcrumbPage>
                </BreadcrumbItem>
              </BreadcrumbList>
            </Breadcrumb>
          </ToolbarHeading>
          <ToolbarActions>
            <Button
              variant="outline"
              onClick={() => exportMutation.mutate(filters)}
              disabled={exportMutation.isPending}
            >
              <Download className="size-4 mr-2" />
              {exportMutation.isPending ? 'Queueing…' : 'Export CSV'}
            </Button>
          </ToolbarActions>
        </Toolbar>
      </Container>

      <Container>
        <Card className="mb-4">
          <CardContent className="pt-6">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
              <div className="space-y-2">
                <Label htmlFor="date_from">From</Label>
                <Input
                  id="date_from"
                  type="datetime-local"
                  value={dateFrom}
                  onChange={(e) => {
                    setDateFrom(e.target.value);
                    resetPaging();
                  }}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="date_to">To</Label>
                <Input
                  id="date_to"
                  type="datetime-local"
                  value={dateTo}
                  onChange={(e) => {
                    setDateTo(e.target.value);
                    resetPaging();
                  }}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="direction">Direction</Label>
                <SearchableSelect
                  options={DIRECTION_OPTIONS}
                  value={direction}
                  onChange={(v) => {
                    setDirection(v);
                    resetPaging();
                  }}
                  placeholder="All directions"
                />
              </div>
              <div className="space-y-2 lg:col-span-2">
                <Label htmlFor="search">Search</Label>
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
                  <Input
                    id="search"
                    className="pl-9"
                    placeholder="Message text, phone, or name"
                    value={search}
                    onChange={(e) => {
                      setSearch(e.target.value);
                      resetPaging();
                    }}
                  />
                </div>
              </div>
            </div>

            <div className="flex items-center gap-2 mt-4">
              <Button
                variant={breachedOnly ? 'primary' : 'outline'}
                size="sm"
                onClick={() => {
                  setBreachedOnly((v) => !v);
                  resetPaging();
                }}
              >
                Breached only
              </Button>
              <span className="text-xs text-muted-foreground">
                Turns whose reply took longer than the p99 target. Shows both the incoming
                message and its reply.
              </span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm" style={{ tableLayout: 'fixed' }}>
                <thead className="border-b bg-muted/40">
                  <tr className="text-left">
                    <th className="px-4 py-3 font-medium" style={{ width: 160 }}>Time</th>
                    <th className="px-4 py-3 font-medium" style={{ width: 220 }}>Contact</th>
                    <th className="px-4 py-3 font-medium" style={{ width: 100 }}>Direction</th>
                    <th className="px-4 py-3 font-medium">Message</th>
                    <th className="px-4 py-3 font-medium" style={{ width: 100 }}>Latency</th>
                    <th className="px-4 py-3 font-medium" style={{ width: 110 }}>Delivery</th>
                  </tr>
                </thead>
                <tbody>
                  {isLoading &&
                    Array.from({ length: 8 }).map((_, i) => (
                      <tr key={i} className="border-b">
                        <td colSpan={6} className="px-4 py-3">
                          <Skeleton className="h-5 w-full" />
                        </td>
                      </tr>
                    ))}

                  {!isLoading && rows.length === 0 && (
                    <tr>
                      <td colSpan={6}>
                        <div className="text-center py-16">
                          <MessageSquare className="size-8 mx-auto text-muted-foreground mb-3" />
                          <p className="font-medium">No messages in this range</p>
                          <p className="text-sm text-muted-foreground mt-1">
                            Widen the date range, or clear the filters. Chat history is
                            written by the n8n WhatsApp flow.
                          </p>
                        </div>
                      </td>
                    </tr>
                  )}

                  {!isLoading &&
                    rows.map((row) => (
                      <tr
                        key={row.id}
                        className="border-b hover:bg-muted/40 cursor-pointer"
                        onClick={() => setSelected(row)}
                      >
                        <td className="px-4 py-3 whitespace-nowrap">
                          {formatDateTimeInMalaysia(row.sent_at)}
                        </td>
                        <td className="px-4 py-3 truncate" title={row.contact_display}>
                          {row.contact_display}
                        </td>
                        <td className="px-4 py-3">
                          <Badge variant={row.type === 'incoming' ? 'secondary' : 'outline'}>
                            {row.type}
                          </Badge>
                        </td>
                        <td className="px-4 py-3 truncate" title={row.message}>
                          {row.message}
                        </td>
                        <td className="px-4 py-3">
                          <LatencyCell seconds={row.latency_seconds} />
                        </td>
                        <td className="px-4 py-3 text-muted-foreground">
                          {row.delivery_status ?? '—'}
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>

            <div className="flex items-center justify-between px-4 py-3 border-t">
              <span className="text-xs text-muted-foreground">
                {isFetching ? 'Loading…' : `Page ${pageIndex + 1} · ${rows.length} messages`}
              </span>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={pageIndex === 0}
                  onClick={() => setPageIndex((i) => Math.max(0, i - 1))}
                >
                  Previous
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!data?.next_cursor}
                  onClick={goNext}
                >
                  Next
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      </Container>

      <ChatThreadDrawer row={selected} onOpenChange={(open) => !open && setSelected(null)} />
    </>
  );
}
