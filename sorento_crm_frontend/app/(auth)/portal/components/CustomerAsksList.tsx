'use client';

import { useMemo, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { AskTodoList } from '@/components/stock-asks/AskTodoList';
import type { AskTodoPayload } from '@/lib/stock-asks-todo';
import type { StockAsk } from '@/lib/stock-asks';
import { useCustomerAsksTodo, usePortalAsksSort } from '../hooks/useCustomerAsksTodo';
import { CustomerAsksHistory } from './CustomerAsksHistory';

function matches(ask: StockAsk, needle: string): boolean {
  return [ask.customer_name, ask.contact_name, ask.product_code].some((v) => v?.toLowerCase().includes(needle));
}

/**
 * Sales-asks-todo S1: the body of the landing's Customer asks kind is the salesperson's to-do
 * (`AskTodoList`, shared with the CRM's Sales > Customer asks), not a paged grid. The landing's
 * search box narrows the to-do; `Show done` opens the paged done history (#1333) under it, so
 * the to-do stays a to-do.
 */
export function CustomerAsksList({ search, contactId }: { search: string; contactId?: string | null }) {
  const todo = useCustomerAsksTodo();
  const [sort, setSort] = usePortalAsksSort(contactId);
  const [showDone, setShowDone] = useState(false);
  const needle = search.trim().toLowerCase();

  const payload = useMemo<AskTodoPayload | null>(() => {
    if (!todo.payload || !needle) return todo.payload;
    return {
      ...todo.payload,
      open: todo.payload.open.filter((a) => matches(a, needle)),
      done_today: todo.payload.done_today.filter((a) => matches(a, needle)),
    };
  }, [todo.payload, needle]);

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
      <AskTodoList
        payload={payload}
        loading={todo.loading}
        error={todo.error}
        onDone={todo.done}
        onReopen={todo.reopen}
        onNote={todo.note}
        sort={sort}
        onSortChange={setSort}
        pendingAskId={todo.pendingAskId}
      />
      <Button variant="ghost" size="sm" onClick={() => setShowDone((v) => !v)} aria-expanded={showDone}>
        {showDone ? 'Hide done' : 'Show done'}
      </Button>
      {showDone ? <CustomerAsksHistory search={search} refreshKey={todo.version} /> : null}
    </div>
  );
}
