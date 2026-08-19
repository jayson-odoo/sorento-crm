import { useMemo } from 'react';
import { useSalesAgents } from '@/app/(protected)/master-data-management/sales-agents/hooks/useSalesAgents';
import type { SearchableSelectOption } from '@/components/common/SearchableSelect';

/**
 * Every sales agent as a `SearchableSelect` option, for the two places on this screen that
 * need to pick one: the list's Agent filter and the detail page's Agent field.
 *
 * Reuses the sales-agents master's own `useSalesAgents` (per ARCHITECTURE-RULES: user/agent
 * selects go through the one shared source, never a per-feature duplicate). That hook is
 * paginated for its own list page; 200 is comfortably above the ~55 codes the master holds
 * today, so this reads as "every agent" without adding a second, options-shaped endpoint.
 *
 * `value` is the id - never shown, only used to address the write. `label` is the code a
 * document actually states, with the person it has been annotated to alongside it when
 * known, since "SEAN I" alone means nothing to a planner who does not have the mapping
 * memorised.
 */
export function useSalesAgentOptions() {
  const agents = useSalesAgents({ pageIndex: 0, pageSize: 200, sorting: [], searchQuery: '' });
  const options = useMemo<SearchableSelectOption[]>(
    () =>
      (agents.data?.data ?? [])
        .slice()
        .sort((a, b) => a.sales_agent.localeCompare(b.sales_agent))
        .map((a) => ({
          value: a.id,
          label: a.person_label ? `${a.sales_agent} · ${a.person_label}` : a.sales_agent,
        })),
    [agents.data],
  );
  return { ...agents, options };
}
