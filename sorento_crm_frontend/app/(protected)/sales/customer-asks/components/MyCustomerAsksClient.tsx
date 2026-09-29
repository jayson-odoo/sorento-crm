'use client';

import { useMemo, useState } from 'react';
import { PageHeader } from '@/components/common/PageHeader';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { AskTodoList } from '@/components/stock-asks/AskTodoList';
import { useListingViewPreferences } from '@/lib/listing-column-preferences/useListingViewPreferences';
import { DEFAULT_ASK_SORT, normalizeSort } from '@/lib/stock-asks-todo';
import { useAskAgentsQuery, useAskDoneMutation, useCustomerAsksTodoQuery } from '../hooks/useCustomerAsksTodo';

const ALL_AGENTS = 'all';
/** The remembered sort lives in the existing per-user view preference row (plan 3.2). */
const SORT_LISTING_KEY = 'sales.customer_asks.view::todo';
const DEFAULT_SORTING = [{ id: DEFAULT_ASK_SORT.id, desc: DEFAULT_ASK_SORT.desc }];

/**
 * Sales > Customer asks: the signed-in salesperson's to-do (the same `AskTodoList` the portal
 * mounts). When the API lists agents the caller may pick (view_all, or a team leader's team) an
 * Agent select shows them with open counts; clearing it returns to mine.
 */
export function MyCustomerAsksClient() {
  const [agentId, setAgentId] = useState('');
  const todo = useCustomerAsksTodoQuery(agentId);
  const agents = useAskAgentsQuery();
  const prefs = useListingViewPreferences({
    listingKey: SORT_LISTING_KEY,
    defaultSorting: DEFAULT_SORTING,
    filtersVersion: 1,
  });
  const sort = normalizeSort(prefs.sorting[0]);
  const canPick = (agents.data?.length ?? 0) > 0;
  const save = useAskDoneMutation();

  const agentOptions = useMemo(
    () => [
      { value: ALL_AGENTS, label: 'All agents' },
      ...(agents.data ?? []).map((a) => ({
        value: a.agent_id,
        label: `${a.code} · ${a.open} open · ${a.needs_attention} need attention`,
        searchText: `${a.code} ${a.name}`,
      })),
    ],
    [agents.data],
  );

  const unlinked = !agentId && todo.data != null && todo.data.agent == null;

  return (
    <div className="space-y-5">
      <PageHeader
        title="Customer asks"
        actions={
          canPick ? (
            <div className="w-full sm:w-80">
              <label htmlFor="customer-asks-agent" className="sr-only">
                Agent
              </label>
              <SearchableSelect
                id="customer-asks-agent"
                value={agentId}
                onChange={setAgentId}
                options={agentOptions}
                placeholder="Agent"
                clearable
                size="sm"
              />
            </div>
          ) : null
        }
      />

      {unlinked ? (
        <div className="rounded-lg border px-6 py-8 text-center text-sm text-muted-foreground">
          You are not linked to a sales agent
        </div>
      ) : (
        <AskTodoList
          payload={todo.data ?? null}
          loading={todo.isLoading || prefs.isLoading}
          sort={sort}
          onSortChange={(next) => prefs.setSorting([{ id: next.id, desc: next.desc }])}
          error={todo.isError ? (todo.error instanceof Error ? todo.error.message : 'Try again shortly.') : null}
          showAgent={Boolean(agentId)}
          onDone={(askId) => save.mutate({ askId, patch: { state: 'done' } })}
          onReopen={(askId) => save.mutate({ askId, patch: { state: 'open' } })}
          onNote={(askId, note) => save.mutate({ askId, patch: { note } })}
        />
      )}
    </div>
  );
}
