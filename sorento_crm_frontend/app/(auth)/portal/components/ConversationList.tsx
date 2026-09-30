'use client';

import { useMemo, useState } from 'react';
import {
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from '@tanstack/react-table';
import {
  AlertCircle,
  ArrowDown,
  ArrowDownLeft,
  ArrowUp,
  ArrowUpRight,
  MessageCircle,
} from 'lucide-react';

import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridTable } from '@/components/ui/data-grid-table';
import {
  Drawer,
  DrawerContent,
  DrawerDescription,
  DrawerHeader,
  DrawerTitle,
} from '@/components/ui/drawer';
import { Skeleton } from '@/components/ui/skeleton';
import type { ListBoardViewMode } from '@/hooks/useListBoardViewPreference';
import {
  formatDateTimeInMalaysia,
  parseDateTimeAsUTC,
  timeAgo,
} from '@/lib/helpers';
import { stripWhatsAppMarkup } from '@/lib/whatsappText';

import {
  usePortalConversationSort,
  usePortalConversations,
} from '../hooks/usePortalConversations';
import {
  CONVERSATION_LANDING_FIELDS,
  conversationToSummary,
} from '../lib/conversation-landing';
import type { PortalConversation } from '../lib/conversations-service';
import {
  activeLandingFilterCount,
  applyLandingFilters,
  sortLandingItems,
  type LandingFilters,
  type LandingSort,
} from '../lib/landing-fields';
import { ConversationThread } from './ConversationThread';
import { LandingCardShell } from './LandingCardShell';
import { LandingToolbar } from './LandingToolbar';

/**
 * The body of the landing's Conversation kind (lane SALES-CONVO): one card per customer
 * contact with a chat, latest message first, under the landing's own `LandingToolbar`; a card
 * or row opens the thread in the bottom Drawer the Customer asks kind already uses. The
 * landing's search box narrows the list server-side; Filter and Sort run over the loaded rows;
 * the sort is remembered per contact. No New button: a conversation is not created here.
 */
export function ConversationList({
  search,
  contactId,
  view,
  onViewChange,
}: {
  search: string;
  contactId?: string | null;
  /** The landing owns the cards / list choice, like for every other kind. */
  view: ListBoardViewMode;
  onViewChange: (mode: ListBoardViewMode) => void;
}) {
  const list = usePortalConversations(search);
  const [sort, setSort] = usePortalConversationSort(contactId);
  const [filters, setFilters] = useState<LandingFilters>({});
  const [opened, setOpened] = useState<PortalConversation | null>(null);

  const summaries = useMemo(
    () => list.rows.map(conversationToSummary),
    [list.rows],
  );
  const visible = useMemo(() => {
    const byId = new Map(list.rows.map((r) => [r.contact_id, r]));
    return sortLandingItems(
      applyLandingFilters(summaries, CONVERSATION_LANDING_FIELDS, filters),
      CONVERSATION_LANDING_FIELDS,
      sort,
    )
      .map((s) => byId.get(s.id))
      .filter((r): r is PortalConversation => Boolean(r));
  }, [list.rows, summaries, filters, sort]);

  // The opened thread follows the refetched row (a newer snippet), not its snapshot.
  const current = useMemo(
    () =>
      opened
        ? (list.rows.find((r) => r.contact_id === opened.contact_id) ?? opened)
        : null,
    [opened, list.rows],
  );

  if (list.notAgent) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-sm text-muted-foreground">
          Conversations are for sales agents only.
        </CardContent>
      </Card>
    );
  }

  const narrowed =
    search.trim() !== '' || activeLandingFilterCount(filters) > 0;

  return (
    <div className="space-y-3">
      <LandingToolbar
        fields={CONVERSATION_LANDING_FIELDS}
        items={summaries}
        filters={filters}
        onFiltersChange={setFilters}
        sort={sort}
        onSortChange={setSort}
        view={view}
        onViewChange={onViewChange}
      />

      {list.loading ? (
        <div className="space-y-2.5" data-testid="conversation-list-loading">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      ) : list.error ? (
        <Alert variant="destructive">
          <AlertIcon>
            <AlertCircle />
          </AlertIcon>
          <AlertTitle>{list.error}</AlertTitle>
          <Button
            variant="outline"
            size="sm"
            className="ml-auto"
            onClick={() => void list.reload()}
          >
            Try again
          </Button>
        </Alert>
      ) : visible.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground space-y-2">
            <MessageCircle className="h-8 w-8 mx-auto" />
            {narrowed ? (
              <>
                <p className="font-semibold text-foreground">
                  {search.trim()
                    ? `No conversation matches "${search.trim()}"`
                    : 'No conversation matches your filters'}
                </p>
                <p>
                  Try the customer&apos;s name, the contact&apos;s name or their
                  phone number.
                </p>
                {activeLandingFilterCount(filters) > 0 ? (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => setFilters({})}
                  >
                    Clear filters
                  </Button>
                ) : null}
              </>
            ) : (
              <>
                <p className="font-semibold text-foreground">
                  No conversations yet
                </p>
                <p>None of your customers has messaged us on WhatsApp.</p>
              </>
            )}
          </CardContent>
        </Card>
      ) : view === 'list' ? (
        <ConversationGrid
          rows={visible}
          sort={sort}
          onSortChange={setSort}
          onOpen={setOpened}
        />
      ) : (
        <ul className="space-y-2.5">
          {visible.map((row) => (
            <li key={row.contact_id}>
              <ConversationCard row={row} onOpen={setOpened} />
            </li>
          ))}
        </ul>
      )}

      <Drawer
        open={Boolean(opened)}
        onOpenChange={(next) => !next && setOpened(null)}
      >
        {/* dvh: phone-facing portal sheet, so a `vh` cap sits under mobile Safari's chrome. */}
        <DrawerContent className="max-h-[90dvh]">
          <DrawerHeader className="sr-only">
            <DrawerTitle>Conversation</DrawerTitle>
            <DrawerDescription>
              The WhatsApp conversation with this customer
            </DrawerDescription>
          </DrawerHeader>
          {current ? (
            <div className="flex min-h-0 flex-1 flex-col px-3 pb-3 pt-1">
              <ConversationThread key={current.contact_id} contact={current} />
            </div>
          ) : null}
        </DrawerContent>
      </Drawer>
    </div>
  );
}

function whenLabel(stamp: string | null): { short: string; full: string } {
  if (!stamp) return { short: '', full: '' };
  const date = parseDateTimeAsUTC(stamp);
  return { short: timeAgo(date), full: formatDateTimeInMalaysia(date) };
}

function snippetText(row: PortalConversation): string {
  return (
    stripWhatsAppMarkup(row.last_message_snippet?.trim() ?? '') ||
    'No messages yet'
  );
}

function DirectionIcon({
  direction,
}: {
  direction: PortalConversation['last_message_direction'];
}) {
  if (direction === 'outgoing') {
    return (
      <ArrowUpRight
        className="size-3.5 shrink-0"
        aria-label="Last message was outgoing"
      />
    );
  }
  if (direction === 'incoming') {
    return (
      <ArrowDownLeft
        className="size-3.5 shrink-0"
        aria-label="Last message was incoming"
      />
    );
  }
  return null;
}

/**
 * One conversation on the landing card shell: the customer, the contact, the phone, the last
 * message with its direction, and when. The whole card opens the thread. A card whose last
 * message came from the customer is tinted and says so: that is the one that needs me.
 */
function ConversationCard({
  row,
  onOpen,
}: {
  row: PortalConversation;
  onOpen: (row: PortalConversation) => void;
}) {
  const waiting = row.last_message_direction === 'incoming';
  const when = whenLabel(row.last_message_at);
  const primary = row.customer_name || row.contact_name || '-';
  const secondary = row.customer_name ? row.contact_name : null;
  return (
    <LandingCardShell
      tintClass={
        waiting ? 'bg-primary/5 border-primary/30' : 'bg-card border-border'
      }
      role="button"
      tabIndex={0}
      data-testid={`conversation-card-${row.contact_id}`}
      onClick={() => onOpen(row)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onOpen(row);
        }
      }}
    >
      {when.short ? (
        <span
          className="absolute top-2 right-3 text-2xs text-muted-foreground"
          title={when.full}
        >
          {when.short}
        </span>
      ) : null}
      <p className="pr-20 text-base break-words">
        <span className="font-semibold">{primary}</span>
        {secondary ? (
          <span className="text-sm text-muted-foreground"> {secondary}</span>
        ) : null}
      </p>
      {row.contact_phone ? (
        <p className="text-xs text-muted-foreground">{row.contact_phone}</p>
      ) : null}
      <p className="mt-1.5 flex items-center gap-1.5 text-sm text-foreground/85">
        <DirectionIcon direction={row.last_message_direction} />
        <span className="min-w-0 truncate" title={snippetText(row)}>
          {snippetText(row)}
        </span>
      </p>
      {waiting ? (
        <Badge variant="warning" className="mt-1.5">
          Customer wrote last
        </Badge>
      ) : null}
    </LandingCardShell>
  );
}

function SortHeader({
  fieldKey,
  label,
  sort,
  onSortChange,
}: {
  fieldKey: string;
  label: string;
  sort: LandingSort;
  onSortChange: (sort: LandingSort) => void;
}) {
  const active = sort.key === fieldKey;
  const isDate = fieldKey === 'last_message_at';
  return (
    <button
      type="button"
      className="flex items-center gap-1 text-left font-medium"
      onClick={(e) => {
        e.stopPropagation();
        onSortChange({
          key: fieldKey,
          dir: active
            ? sort.dir === 'asc'
              ? 'desc'
              : 'asc'
            : isDate
              ? 'desc'
              : 'asc',
        });
      }}
    >
      <span>{label}</span>
      {active &&
        (sort.dir === 'asc' ? (
          <ArrowUp className="size-3.5 text-muted-foreground" />
        ) : (
          <ArrowDown className="size-3.5 text-muted-foreground" />
        ))}
    </button>
  );
}

/** The list view: the system DataGrid, a header click drives the same sort the toolbar writes. */
function ConversationGrid({
  rows,
  sort,
  onSortChange,
  onOpen,
}: {
  rows: PortalConversation[];
  sort: LandingSort;
  onSortChange: (sort: LandingSort) => void;
  onOpen: (row: PortalConversation) => void;
}) {
  const columns = useMemo<ColumnDef<PortalConversation>[]>(() => {
    const header = (fieldKey: string, label: string) => {
      function ConversationHeader() {
        return (
          <SortHeader
            fieldKey={fieldKey}
            label={label}
            sort={sort}
            onSortChange={onSortChange}
          />
        );
      }
      return ConversationHeader;
    };
    const text = (value: string | null | undefined) => (
      <span className="block truncate" title={value ?? undefined}>
        {value || '-'}
      </span>
    );
    return [
      {
        id: 'customer_name',
        header: header('customer_name', 'Customer'),
        size: 180,
        minSize: 100,
        cell: ({ row }) => text(row.original.customer_name),
      },
      {
        id: 'contact_name',
        header: header('contact_name', 'Contact'),
        size: 130,
        minSize: 90,
        cell: ({ row }) => text(row.original.contact_name),
      },
      {
        id: 'last_message',
        header: 'Last message',
        size: 320,
        minSize: 140,
        cell: ({ row }) => (
          <span
            className="flex items-center gap-1.5 min-w-0"
            title={snippetText(row.original)}
          >
            <DirectionIcon direction={row.original.last_message_direction} />
            <span className="min-w-0 truncate">
              {snippetText(row.original)}
            </span>
          </span>
        ),
      },
      {
        id: 'last_message_at',
        header: header('last_message_at', 'When'),
        size: 150,
        minSize: 110,
        cell: ({ row }) => text(whenLabel(row.original.last_message_at).full),
      },
    ];
  }, [sort, onSortChange]);

  const table = useReactTable({
    data: rows,
    columns,
    getRowId: (r) => r.contact_id,
    getCoreRowModel: getCoreRowModel(),
    columnResizeMode: 'onChange',
  });

  return (
    <DataGrid
      table={table}
      recordCount={rows.length}
      // Columns are fixed and the portal has no user row to key a preference on.
      listingKey={null}
      tableLayout={{ width: 'fixed', columnsResizable: true }}
      onRowClick={onOpen}
    >
      <DataGridTable />
    </DataGrid>
  );
}
