import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { getCustomerAsksTodo, listAskAgents, updateSalesAsk } from '@/services/stockAskService';
import type { StockAskPatch } from '@/lib/stock-asks';

const TODO_KEY = 'customer-asks-todo';
const AGENTS_KEY = 'customer-asks-agents';

/** The to-do of the signed-in salesperson, or (view_all) one agent / 'all'. '' = mine. */
export function useCustomerAsksTodoQuery(agentId: string) {
  return useQuery({
    queryKey: [TODO_KEY, agentId],
    queryFn: () => getCustomerAsksTodo(agentId || undefined),
  });
}

/** The agents the caller may pick (view_all, or a team leader's team); `[]` renders no select. */
export function useAskAgentsQuery() {
  return useQuery({
    queryKey: [AGENTS_KEY],
    queryFn: listAskAgents,
  });
}

/** Done, Reopen and Note all patch one ask; invalidate both the to-do and the agent counts. */
export function useAskDoneMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ askId, patch }: { askId: string; patch: StockAskPatch }) => updateSalesAsk(askId, patch),
    onSuccess: (_ask, { patch }) => {
      queryClient.invalidateQueries({ queryKey: [TODO_KEY] });
      queryClient.invalidateQueries({ queryKey: [AGENTS_KEY] });
      queryClient.invalidateQueries({ queryKey: ['customer-asks'] });
      toast.success(
        patch.state === 'done' ? 'Marked done' : patch.state === 'open' ? 'Reopened' : 'Note saved',
      );
    },
    onError: (error: unknown) => {
      toast.error(error instanceof Error ? error.message : 'Failed to update the ask');
    },
  });
}
