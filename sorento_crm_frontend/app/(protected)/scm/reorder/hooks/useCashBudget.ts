'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import { fmtMoney } from '../../lib/format';

/**
 * The company's configured cash budget (`scm.purchasing_budget`).
 *
 * Read separately from the plan because it is a STANDING figure, not a property of one run:
 * the same limit constrains every plan until somebody changes it. `configured: false` is a
 * real answer and the plan must not paper over it with a guess.
 */
export interface CashBudget {
  configured: boolean;
  budget_amount: number | null;
  currency: string | null;
  period_start: string | null;
  period_end: string | null;
  note: string | null;
  set_by: string | null;
}

const KEY = ['scm', 'config', 'cash-budget'] as const;

export function useCashBudget(enabled = true) {
  return useQuery({
    queryKey: KEY,
    enabled,
    queryFn: async (): Promise<CashBudget> => {
      const res = await apiFetch('/api/v1/scm/config/cash-budget');
      if (!res.ok) throw new Error(await extractApiError(res, 'Failed to load the cash budget'));
      return (await res.json()) as CashBudget;
    },
    staleTime: 5 * 60_000,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useSaveCashBudget() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: { budget_amount: number | null; note?: string }) => {
      const res = await apiFetch('/api/v1/scm/config/cash-budget', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(await extractApiError(res, 'Failed to save the cash budget'));
      return (await res.json()) as CashBudget;
    },
    onSuccess: (data) => {
      qc.setQueryData(KEY, data);
      toast.success(
        data.configured
          ? `Cash budget saved: ${fmtMoney(data.budget_amount ?? 0)}.`
          : 'Cash budget cleared. The plan now shows in full.',
      );
    },
    onError: (e: Error) => toast.error(e.message),
  });
}
