'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { formatDateInMalaysia } from '@/lib/helpers';
import { toast } from '@/lib/toast';
import { changeAreaDate, getPurchaseOrderProgress } from '../services/poProgressService';
import type { AreaDateChangeBody, AreaDateChangeResult } from '../types/poProgress.types';
import { SALES_ORDERS_KEY } from './useProjectSalesOrders';
import { POS_KEY } from './useProjects';

export const PO_PROGRESS_KEY = 'project-po-progress';

export const poProgressKey = (poId: string) => [PO_PROGRESS_KEY, poId];

export function usePurchaseOrderProgress(poId: string | undefined) {
  return useQuery({
    queryKey: poProgressKey(poId ?? ''),
    queryFn: () => getPurchaseOrderProgress(poId as string),
    enabled: Boolean(poId),
  });
}

/** What moved, in one sentence: the area, its new date, and what followed (AC-D3). */
export function describeAreaDateChange(result: AreaDateChangeResult): string {
  const area = [result.area_group, result.label].filter(Boolean).join(', ');
  const when = result.delivery_date ? formatDateInMalaysia(result.delivery_date) : 'no date';
  const parts = [`${area} moves to ${when}.`];
  if (result.moved_orders.length > 0) {
    const refs = result.moved_orders.map((order) => order.provisional_ref).join(', ');
    parts.push(
      `${refs} ${result.moved_orders.length === 1 ? 'is' : 'are'} not published, so ${
        result.moved_lines === 1 ? 'its line takes' : 'their lines take'
      } the new date.`,
    );
  }
  const amended = result.amendments.filter((row) => row.amendment_id);
  const refused = result.amendments.filter((row) => row.refused);
  if (amended.length > 0) {
    parts.push(
      `An amendment is proposed for ${amended.map((row) => row.provisional_ref).join(', ')}.`,
    );
  }
  for (const row of refused) parts.push(`${row.provisional_ref}: ${row.refused}`);
  if (amended.length === 0 && refused.length === 0) parts.push('Nothing published changes.');
  return parts.join(' ');
}

/**
 * Move one area's date (Q2a). No confirm dialog: the change is reversible, so the toast
 * carries Undo, which sends the previous date and every line's own previous date back.
 */
export function useChangeAreaDate(projectId: string, poId: string) {
  const queryClient = useQueryClient();
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: poProgressKey(poId) });
    queryClient.invalidateQueries({ queryKey: [POS_KEY, projectId] });
    queryClient.invalidateQueries({ queryKey: [SALES_ORDERS_KEY, projectId] });
  };

  const mutation = useMutation({
    mutationFn: ({ phaseId, body }: { phaseId: string; body: AreaDateChangeBody }) =>
      changeAreaDate(phaseId, body),
    onSuccess: (result, variables) => {
      invalidate();
      if (variables.body.restore_lines) {
        toast.success('Undone.');
        return;
      }
      toast.success(describeAreaDateChange(result), {
        duration: 10000,
        action:
          result.previous_date !== result.delivery_date || result.previous_lines.length > 0
            ? {
                label: 'Undo',
                onClick: () =>
                  mutation.mutate({
                    phaseId: result.phase_id,
                    body: {
                      // Null gives an area that had no date its blank back.
                      delivery_date: result.previous_date,
                      restore_lines: result.previous_lines,
                    },
                  }),
              }
            : undefined,
      });
    },
    onError: (error: Error) => toast.error(error.message),
  });
  return mutation;
}
