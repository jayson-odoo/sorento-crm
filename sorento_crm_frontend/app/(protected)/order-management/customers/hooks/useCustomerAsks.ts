import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';
import { listCustomerAsks, updateCustomerAsk } from '@/services/stockAskService';
import type { StockAskPatch } from '@/lib/stock-asks';

/** Chatbot stock ask v2 S5: one customer's stock asks, a page at a time. */
export function useCustomerAsksQuery(
  customerId: string,
  pagination: { pageIndex: number; pageSize: number },
) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: ['customer-asks', customerId, pagination.pageIndex, pagination.pageSize],
    queryFn: () => listCustomerAsks(customerId, pagination),
    enabled: Boolean(customerId),
  });
}

export function useUpdateAskMutation(customerId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ askId, patch }: { askId: string; patch: StockAskPatch }) =>
      updateCustomerAsk(customerId, askId, patch),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['customer-asks', customerId] });
      toast.success('Ask updated');
    },
    onError: (error: unknown) => {
      toast.error(error instanceof Error ? error.message : 'Failed to update the ask');
    },
  });
}
