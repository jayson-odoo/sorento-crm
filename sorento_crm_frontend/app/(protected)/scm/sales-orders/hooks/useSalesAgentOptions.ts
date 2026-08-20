import { useMemo } from 'react';
import { useSalesOrderAgents } from '../../hooks/useSalesOrders';
import type { SearchableSelectOption } from '@/components/common/SearchableSelect';

/**
 * Every sales agent as a `SearchableSelect` option, for the two places on this screen that
 * need to pick one: the list's Agent filter and the detail page's Agent field.
 *
 * Reads `GET /scm/sales-orders/agents` (`useSalesOrderAgents`) rather than the sales-agents
 * master's own `useSalesAgents` (`master_data.sales_agents.view`): a role that can read SCM
 * sales orders - e.g. Purchasing, gated on `scm.dashboard.view` - does not necessarily hold
 * the master-data permission too, and 403'd on this select alone when it did. The sales
 * order router serves the same rows under its own read gate instead.
 *
 * `value` is the id - never shown, only used to address the write. `label` is the code a
 * document actually states, with the person it has been annotated to alongside it when
 * known, since "SEAN I" alone means nothing to a planner who does not have the mapping
 * memorised.
 */
export function useSalesAgentOptions() {
  const agents = useSalesOrderAgents();
  const options = useMemo<SearchableSelectOption[]>(
    () =>
      (agents.data ?? [])
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
