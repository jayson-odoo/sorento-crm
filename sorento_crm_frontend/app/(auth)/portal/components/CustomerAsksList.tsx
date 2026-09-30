'use client';

import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import {
  Drawer,
  DrawerContent,
  DrawerDescription,
  DrawerHeader,
  DrawerTitle,
} from '@/components/ui/drawer';
import { AskConversationPanel } from '@/components/stock-asks/AskConversationPanel';
import { AskTodoList } from '@/components/stock-asks/AskTodoList';
import type { ListBoardViewMode } from '@/hooks/useListBoardViewPreference';
import type { StockAsk } from '@/lib/stock-asks';
import {
  ASK_LANDING_FIELDS,
  askToSummary,
  filterTodoPayload,
} from '@/lib/stock-asks-todo';
import { useCustomerAsksTodo, usePortalAskThread, usePortalAsksSort } from '../hooks/useCustomerAsksTodo';
import { getAskConversation } from '../lib/customer-asks-service';
import type { LandingFilters } from '../lib/landing-fields';
import { CustomerAsksHistory } from './CustomerAsksHistory';
import { LandingToolbar } from './LandingToolbar';

/**
 * The body of the landing's Customer asks kind: the salesperson's to-do (`AskTodoList`, shared
 * with the CRM's Sales > Customer asks) under the landing's own `LandingToolbar`. A card or row
 * opens the conversation in a bottom Drawer; `Show done` opens the paged done history under it,
 * as cards or as the grid, whichever the view is (ASKS-UX item 2). The landing's search box
 * narrows the to-do; the sort is remembered per contact.
 */
export function CustomerAsksList({
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
  const todo = useCustomerAsksTodo();
  const [sort, setSort] = usePortalAsksSort(contactId);
  const [filters, setFilters] = useState<LandingFilters>({});
  const [showDone, setShowDone] = useState(false);
  const [opened, setOpened] = useState<StockAsk | null>(null);

  const items = useMemo(
    () => (todo.payload ? [...todo.payload.open, ...todo.payload.done_today].map(askToSummary) : []),
    [todo.payload],
  );
  const payload = useMemo(
    () => (todo.payload ? filterTodoPayload(todo.payload, filters, search) : null),
    [todo.payload, filters, search],
  );

  // The opened card follows the refetched row (a saved note, a state change), not its snapshot.
  const current = useMemo(() => {
    if (!opened) return null;
    const all = todo.payload ? [...todo.payload.open, ...todo.payload.done_today] : [];
    return all.find((a) => a.id === opened.id) ?? opened;
  }, [opened, todo.payload]);

  // The anchor (`ask_message_ref`) and the contact's thread, both keyed on the opened ask; the
  // thread is the ticket drawer's shared component fed by the portal loaders (ASKS-UX item 3).
  const conversation = useQuery({
    queryKey: ['portal-customer-ask-conversation', opened?.id],
    queryFn: () => getAskConversation(opened!.id),
    enabled: Boolean(opened),
  });
  const thread = usePortalAskThread(opened?.id ?? null);

  const open = (ask: StockAsk) => setOpened(ask);

  if (todo.notAgent) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-sm text-muted-foreground">
          Customer asks are for sales agents only.
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <LandingToolbar
        fields={ASK_LANDING_FIELDS}
        items={items}
        filters={filters}
        onFiltersChange={setFilters}
        sort={sort}
        onSortChange={setSort}
        view={view}
        onViewChange={onViewChange}
      />
      <AskTodoList
        payload={payload}
        loading={todo.loading}
        error={todo.error}
        view={view}
        filtered={Object.keys(filters).length > 0 || search.trim() !== ''}
        sort={sort}
        onSortChange={setSort}
        onOpen={open}
        onDone={todo.done}
        onReopen={todo.reopen}
        pendingAskId={todo.pendingAskId}
        listingKey={null}
      />
      <Button variant="ghost" size="sm" onClick={() => setShowDone((v) => !v)} aria-expanded={showDone}>
        {showDone ? 'Hide done' : 'Show done'}
      </Button>
      {showDone ? (
        <CustomerAsksHistory
          search={search}
          refreshKey={todo.version}
          view={view}
          onOpen={open}
          onReopen={todo.reopen}
          pendingAskId={todo.pendingAskId}
        />
      ) : null}

      <Drawer open={Boolean(opened)} onOpenChange={(next) => !next && setOpened(null)}>
        {/* M6-02: dvh - phone-facing portal sheet, so a `vh` cap sits under mobile Safari's chrome. */}
        <DrawerContent className="max-h-[90dvh]">
          <DrawerHeader className="sr-only">
            <DrawerTitle>Customer ask</DrawerTitle>
            <DrawerDescription>The conversation around this ask</DrawerDescription>
          </DrawerHeader>
          {current ? (
            <AskConversationPanel
              key={current.id}
              ask={current}
              conversation={conversation.data}
              thread={thread}
              showOpenInConversations={false}
              onNote={todo.note}
              onDone={(askId) => {
                todo.done(askId);
                setOpened(null);
              }}
              onReopen={(askId) => {
                todo.reopen(askId);
                setOpened(null);
              }}
              pending={todo.pendingAskId === current.id}
            />
          ) : null}
        </DrawerContent>
      </Drawer>
    </div>
  );
}
