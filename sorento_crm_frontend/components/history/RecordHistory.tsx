'use client';

import * as React from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { DateRangePicker } from '@/components/ui/date-range-picker';
import { Skeleton } from '@/components/ui/skeleton';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { EventTimeline, type TimelineEvent } from '@/components/common/EventTimeline';
import { formatDateInMalaysia } from '@/lib/helpers';

/**
 * STANDARD-HISTORY (`documentation/plans/audit/PLAN-standard-history-10nov.md`): the one
 * History body a record's History tab renders. Owner, 10 Nov 12:41: "just use back existing
 * components that we had in the system, don't invent new things" - so this is the SO History
 * drawer's own body (`PlanningHistorySheet.tsx`) lifted out of its Sheet: the same filters
 * (SearchableSelect / SearchableMultiSelect / DateRangePicker / Clear), the same
 * `EventTimeline`, the same light `Badge`, and the same expand-to-lines table. Nothing here
 * is a new visual.
 *
 * A batch press (one Unconfirm that moved 9 lines) is ONE event whose `lines` name every
 * row; a Product or Line filter narrows the lines shown and keeps the event whole.
 */
export interface RecordHistoryLine {
  row_id: string;
  so_line_no: number | null;
  item_code: string | null;
  qty: number | null;
  change: string;
}

export interface RecordHistoryEvent {
  id: string;
  kind: string;
  at: string | null;
  actor: string | null;
  title: string;
  lines: RecordHistoryLine[];
}

type Tone = 'destructive' | 'info' | 'warning' | 'secondary' | 'success';

export interface RecordHistoryProps {
  events: RecordHistoryEvent[];
  /** The Event filter's options and each event's badge text, by `kind`. */
  kindLabels: Record<string, string>;
  /** Badge tone by `kind`; anything not named reads `secondary`. */
  kindTones?: Record<string, Tone>;
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
  /** Product and Line selects. Off where the history is already one line's (AC-SH-B12). */
  lineFilters?: boolean;
}

/** dd/mm/yyyy (Malaysia) -> yyyy-mm-dd, the DateRangePicker's own value shape. */
function isoDay(at: string | null): string | null {
  if (!at) return null;
  const [d, m, y] = formatDateInMalaysia(at).split('/');
  return y && m && d ? `${y}-${m}-${d}` : null;
}

function LinesTable({ lines }: { lines: RecordHistoryLine[] }) {
  if (lines.length === 0) return null;
  return (
    <div className="mt-2 overflow-x-auto">
      <Table className="text-xs">
        <TableHeader>
          <TableRow>
            {['Line', 'Product', 'Qty', 'Change'].map((name) => (
              <TableHead key={name} className="h-8 px-2">
                {name}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {lines.map((line) => (
            <TableRow key={line.row_id}>
              <TableCell className="px-2 py-1.5 break-words">{line.so_line_no ?? ''}</TableCell>
              <TableCell className="px-2 py-1.5 break-words">{line.item_code ?? ''}</TableCell>
              <TableCell className="px-2 py-1.5 break-words">{line.qty ?? ''}</TableCell>
              <TableCell className="px-2 py-1.5 break-words">{line.change}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

export function RecordHistory({
  events,
  kindLabels,
  kindTones = {},
  isLoading,
  isError,
  onRetry,
  lineFilters = true,
}: RecordHistoryProps) {
  const [product, setProduct] = React.useState<string | null>(null);
  const [line, setLine] = React.useState<string | null>(null);
  const [kinds, setKinds] = React.useState<string[]>([]);
  const [user, setUser] = React.useState<string | null>(null);
  const [range, setRange] = React.useState<{ from: string | null; to: string | null }>({
    from: null,
    to: null,
  });
  const [expanded, setExpanded] = React.useState<Set<string>>(new Set());

  const options = React.useMemo(() => {
    const products = new Set<string>();
    const lineNos = new Set<number>();
    const users = new Set<string>();
    const kindsSeen = new Set<string>();
    events.forEach((event) => {
      kindsSeen.add(event.kind);
      if (event.actor) users.add(event.actor);
      event.lines.forEach((entry) => {
        if (entry.item_code) products.add(entry.item_code);
        if (entry.so_line_no != null) lineNos.add(entry.so_line_no);
      });
    });
    const text = (value: string) => ({ value, label: value });
    return {
      kind: [...kindsSeen].map((value) => ({ value, label: kindLabels[value] ?? value })),
      product: [...products].sort().map(text),
      line: [...lineNos].sort((a, b) => a - b).map((n) => text(String(n))),
      user: [...users].sort().map(text),
    };
  }, [events, kindLabels]);

  const visible = React.useMemo(() => {
    const out: { event: RecordHistoryEvent; lines: RecordHistoryLine[] }[] = [];
    for (const event of events) {
      if (kinds.length > 0 && !kinds.includes(event.kind)) continue;
      if (user && event.actor !== user) continue;
      const day = isoDay(event.at);
      if (range.from && (!day || day < range.from)) continue;
      if (range.to && (!day || day > range.to)) continue;
      let lines = event.lines;
      if (product) lines = lines.filter((entry) => entry.item_code === product);
      if (line) lines = lines.filter((entry) => String(entry.so_line_no) === line);
      if ((product || line) && lines.length === 0) continue;
      out.push({ event, lines });
    }
    return out;
  }, [events, kinds, user, range, product, line]);

  const timeline: TimelineEvent[] = visible.map(({ event, lines }) => {
    const isOpen = expanded.has(event.id);
    return {
      id: event.id,
      testId: `history-event-${event.id}`,
      at: event.at,
      actor: event.actor,
      title:
        event.lines.length > 0 ? (
          <button
            type="button"
            aria-expanded={isOpen}
            className="flex items-center gap-1 text-start"
            onClick={() =>
              setExpanded((current) => {
                const next = new Set(current);
                if (next.has(event.id)) next.delete(event.id);
                else next.add(event.id);
                return next;
              })
            }
          >
            {isOpen ? (
              <ChevronDown className="size-3.5 shrink-0" aria-hidden />
            ) : (
              <ChevronRight className="size-3.5 shrink-0" aria-hidden />
            )}
            <span>{event.title}</span>
          </button>
        ) : (
          event.title
        ),
      tags: (
        <Badge variant={kindTones[event.kind] ?? 'secondary'} appearance="light" size="sm">
          {kindLabels[event.kind] ?? event.kind}
        </Badge>
      ),
      detail: isOpen ? <LinesTable lines={lines} /> : undefined,
    };
  });

  const clearAll = () => {
    setProduct(null);
    setLine(null);
    setKinds([]);
    setUser(null);
    setRange({ from: null, to: null });
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {lineFilters ? (
          <>
            <SearchableSelect
              clearable
              value={product ?? ''}
              onChange={(next) => setProduct(next || null)}
              options={options.product}
              placeholder="Product"
              aria-label="Product"
            />
            <SearchableSelect
              clearable
              value={line ?? ''}
              onChange={(next) => setLine(next || null)}
              options={options.line}
              placeholder="Line"
              aria-label="Line"
            />
          </>
        ) : null}
        <SearchableMultiSelect
          clearable
          value={kinds}
          onChange={setKinds}
          options={options.kind}
          placeholder="Event"
          id="record-history-event-filter"
        />
        <SearchableSelect
          clearable
          value={user ?? ''}
          onChange={(next) => setUser(next || null)}
          options={options.user}
          placeholder="User"
          aria-label="User"
        />
        <DateRangePicker
          from={range.from}
          to={range.to}
          onChange={setRange}
          aria-label="Date range"
        />
        <div>
          <Button type="button" variant="ghost" size="sm" onClick={clearAll}>
            Clear
          </Button>
        </div>
      </div>
      {isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
        </div>
      ) : isError ? (
        <div className="py-10 text-center">
          <h3 className="text-sm font-semibold">Could not load the history</h3>
          <Button type="button" variant="outline" size="sm" className="mt-3" onClick={onRetry}>
            Retry
          </Button>
        </div>
      ) : events.length === 0 ? (
        <div className="py-10 text-center">
          <h3 className="text-sm font-semibold">No history</h3>
          <p className="mt-1 text-sm text-muted-foreground">Nothing recorded for this record yet.</p>
        </div>
      ) : timeline.length === 0 ? (
        <div className="py-10 text-center">
          <h3 className="text-sm font-semibold">No events match</h3>
        </div>
      ) : (
        <div data-testid="history-timeline">
          <EventTimeline events={timeline} />
        </div>
      )}
    </div>
  );
}
