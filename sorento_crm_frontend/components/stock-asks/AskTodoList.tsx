'use client';

import { useMemo } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { MessageSquareText } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { AskedAtCell, AskNoteCell } from '@/components/stock-asks/AskEditCells';
import { NOOP_ON_UPDATE, surfaceExitTransition, useReducedMotion } from '@/lib/motion';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { BRANCH_LABEL, BRANCH_VARIANT, notifiedLabel, type StockAsk } from '@/lib/stock-asks';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import {
  ASK_SORT_OPTIONS,
  DEFAULT_ASK_SORT,
  ageLabel,
  bucketTodo,
  normalizeSort,
  sortToValue,
  type AskSort,
  type AskTodoPayload,
} from '@/lib/stock-asks-todo';
import { cn } from '@/lib/utils';

export interface AskTodoListProps {
  payload: AskTodoPayload | null;
  loading: boolean;
  error?: string | null;
  onDone: (askId: string) => void;
  onReopen: (askId: string) => void;
  onNote: (askId: string, note: string) => void;
  /** The CRM manager page: name the agent on line 1 of each row. */
  showAgent?: boolean;
  /** Orders the rows inside every day. The mount owns where it is remembered. */
  sort?: AskSort;
  onSortChange?: (sort: AskSort) => void;
}

/**
 * The salesperson's to-do of their customers' asks, shared by the portal Customer asks tab and
 * Sales > Customer asks in the CRM. Presentational: the mount fetches, this groups (one pure
 * function, `bucketTodo`) and renders. One action per row, the row leaves the list.
 */
export function AskTodoList({ payload, loading, error, onDone, onReopen, onNote, showAgent = false, sort = DEFAULT_ASK_SORT, onSortChange }: AskTodoListProps) {
  const reduced = useReducedMotion();
  const bucketed = useMemo(() => (payload ? bucketTodo(payload, sort) : null), [payload, sort]);

  if (error) {
    return (
      <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-6 py-10 text-center">
        <h2 className="text-sm font-semibold text-destructive">The asks could not be loaded</h2>
        <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">{error}</p>
      </div>
    );
  }
  if (loading && !bucketed) {
    return (
      <div className="space-y-2" role="status" aria-label="Loading">
        <Skeleton className="h-5 w-64" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }
  if (!payload || !bucketed) return null;

  const { counts, sections, done } = bucketed;
  const exit = { opacity: 0, transition: surfaceExitTransition(reduced) };

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-muted-foreground" data-testid="ask-todo-counts">
          Open <span className="font-semibold tabular-nums text-foreground">{counts.open}</span>
          {' · '}
          Needs attention{' '}
          <span
            className={cn(
              'font-semibold tabular-nums',
              counts.needs_attention > 0 ? 'text-destructive' : 'text-foreground',
            )}
          >
            {counts.needs_attention}
          </span>
          {' · '}
          Done today <span className="font-semibold tabular-nums text-foreground">{counts.done_today}</span>
        </p>
        <div className="w-full sm:w-48">
          <label htmlFor="ask-todo-sort" className="sr-only">
            Sort
          </label>
          <SearchableSelect
            id="ask-todo-sort"
            value={sortToValue(normalizeSort(sort))}
            onChange={(v) => {
              const hit = ASK_SORT_OPTIONS.find((o) => o.value === v);
              if (hit) onSortChange?.(hit.sort);
            }}
            options={ASK_SORT_OPTIONS.map(({ value, label }) => ({ value, label }))}
            size="sm"
          />
        </div>
      </div>

      {counts.open === 0 ? (
        <div className="space-y-2 rounded-lg border px-6 py-8 text-center">
          <MessageSquareText className="mx-auto size-8 text-muted-foreground" />
          <p className="font-medium">Nothing waiting</p>
          <p className="text-sm text-muted-foreground">Asks your customers make on WhatsApp land here.</p>
        </div>
      ) : null}

      {sections.map((section) => (
        <section key={section.key} aria-labelledby={`ask-section-${section.key}`} className="space-y-3">
          <h2
            id={`ask-section-${section.key}`}
            className={cn('text-sm font-semibold', section.key === 'needs_attention' && 'text-destructive')}
          >
            {section.label}
          </h2>
          {section.days.map((day) => (
            <div key={day.key} className="space-y-2">
              <h3 className="text-xs font-medium text-muted-foreground">{day.label}</h3>
              <ul className="space-y-2.5">
                <AnimatePresence initial={false}>
                  {day.asks.map((ask) => (
                    <motion.li key={ask.id} exit={exit} onUpdate={NOOP_ON_UPDATE} className="rounded-lg border">
                      <AskRow
                        ask={ask}
                        todayStart={payload.today_start}
                        showAge={section.key === 'needs_attention'}
                        showAgent={showAgent}
                        onDone={() => onDone(ask.id)}
                        onNote={(note) => onNote(ask.id, note)}
                      />
                    </motion.li>
                  ))}
                </AnimatePresence>
              </ul>
            </div>
          ))}
        </section>
      ))}

      {payload.truncated ? (
        <p className="text-sm text-muted-foreground">Showing the oldest 500 open asks</p>
      ) : null}

      {done.length > 0 ? (
        <section aria-labelledby="ask-group-done" className="space-y-2">
          <h2 id="ask-group-done" className="text-sm font-semibold">
            Done today
          </h2>
          <ul className="space-y-2.5">
            {done.map((ask) => (
              <li key={ask.id} className="rounded-lg border">
                <AskRow
                  ask={ask}
                  todayStart={payload.today_start}
                  showAge={false}
                  showAgent={showAgent}
                  onReopen={() => onReopen(ask.id)}
                  onNote={(note) => onNote(ask.id, note)}
                />
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}

/**
 * One ask. Line 1 customer and contact, line 2 the product and the branch, line 3 the chatbot's
 * answer, line 4 when it was asked. Actions sit right at 1280px and under the text at 375px.
 * A done row (no `onDone`) is greyed and offers Reopen.
 */
function AskRow({
  ask,
  todayStart,
  showAge,
  showAgent,
  onDone,
  onReopen,
  onNote,
}: {
  ask: StockAsk;
  todayStart: string;
  showAge: boolean;
  showAgent: boolean;
  onDone?: () => void;
  onReopen?: () => void;
  onNote: (note: string) => void;
}) {
  const notified = notifiedLabel(ask);
  const isDone = ask.state === 'done';
  const age = showAge ? ageLabel(ask.created_at, todayStart) : '';
  return (
    <div className="grid gap-3 px-3.5 py-3 sm:grid-cols-[1fr_auto] sm:items-start">
      <div className={cn('min-w-0 space-y-1', isDone && 'opacity-60')}>
        <p className="min-w-0 text-sm break-words">
          {showAgent && ask.agent_code ? (
            <span className="mr-1.5 font-medium text-muted-foreground">{ask.agent_code}</span>
          ) : null}
          <span className="font-semibold">{ask.customer_name || '-'}</span>
          {ask.contact_name ? <span className="text-muted-foreground"> {ask.contact_name}</span> : null}
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium tabular-nums" title={ask.product_name ?? ask.product_code}>
            {ask.product_code} x {ask.quantity}
          </span>
          <Badge variant={BRANCH_VARIANT[ask.branch] ?? 'secondary'} appearance="light">
            {BRANCH_LABEL[ask.branch] ?? ask.branch}
          </Badge>
        </div>
        <p className="truncate text-sm text-foreground/80" title={ask.answer_summary}>
          {ask.answer_summary}
        </p>
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
          <AskedAtCell ask={ask} />
          {age ? <span className="font-medium text-destructive">{age}</span> : null}
          <Badge variant={notified.variant} appearance="light" title={notified.title}>
            {notified.label}
          </Badge>
        </div>
        {isDone ? (
          <p className="text-xs text-muted-foreground">
            {ask.done_by ? `Done by ${ask.done_by}` : 'Done'}
            {ask.done_at ? ` ${formatDateTimeInMalaysia(ask.done_at)}` : ''}
          </p>
        ) : null}
      </div>
      <div className="flex flex-col gap-2 sm:w-56">
        {onDone ? (
          <Button size="sm" variant="primary" className="w-full" onClick={onDone}>
            Done
          </Button>
        ) : null}
        {onReopen ? (
          <Button size="sm" variant="outline" className="w-full" onClick={onReopen}>
            Reopen
          </Button>
        ) : null}
        <AskNoteCell ask={ask} editable onSave={(patch) => onNote(patch.note ?? '')} />
      </div>
    </div>
  );
}
