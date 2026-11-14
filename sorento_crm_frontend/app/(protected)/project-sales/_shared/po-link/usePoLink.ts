'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
// The switch read goes through the Stock Debt service's re-export: its drill tests mock it there.
import { getPoLinkSwitch } from '../../stock-debt/services/stockDebtSnapshotService';
import type { ResumePoLinkInput } from './poLinkService';
import type { PoLinkTarget } from './poLink.types';

/** What AutoCount can do now and the open PO lines of the product. Read only while the menu or
 *  the popup is open, so the capabilities are always fresh. */
export function usePoLinkOptions(target: PoLinkTarget, enabled: boolean) {
  return useQuery({
    queryKey: [...target.key],
    queryFn: () => target.api.options(),
    enabled,
    staleTime: 0,
    retry: false,
  });
}

/** The PO link writes. Each answers per line; the screen's data and the options are read again
 *  after every call so it shows what AutoCount returned. */
export function usePoLinkMutations(target: PoLinkTarget) {
  const queryClient = useQueryClient();
  const refresh = () => {
    target.refresh?.(queryClient);
    queryClient.invalidateQueries({ queryKey: [...target.key] });
  };
  const onError = (error: Error) => toast.error(error.message);
  return {
    link: useMutation({
      mutationFn: (lines: Parameters<PoLinkTarget['api']['link']>[0]) => target.api.link(lines),
      onSuccess: refresh,
      onError,
    }),
    unlink: useMutation({
      mutationFn: (ids: string[]) => target.api.unlink(ids),
      onSuccess: refresh,
      onError,
    }),
    relink: useMutation({
      mutationFn: (moves: Array<{ po_line_id: string; to_sales_order_line_id: string }>) => {
        if (!target.api.relink) throw new Error('Moving a PO is not available here');
        return target.api.relink(moves);
      },
      onSuccess: refresh,
      onError,
    }),
    change: useMutation({
      mutationFn: (changes: Parameters<PoLinkTarget['api']['change']>[0]) => target.api.change(changes),
      onSuccess: refresh,
      onError,
    }),
    relocate: useMutation({
      mutationFn: (poLineId: string) => target.api.relocate(poLineId),
      onSuccess: refresh,
      onError,
    }),
    resume: useMutation({
      mutationFn: (input: ResumePoLinkInput) => target.api.resume(input),
      onSuccess: refresh,
      onError,
    }),
  };
}

/** "AutoCount PO links" (System Settings), shared by Stock Debt and Order Inquiries. Read only
 *  for a link_po holder. */
export function usePoLinkSwitch(enabled: boolean) {
  return useQuery({
    queryKey: ['system-app-config', 'stock-debt-po-link'],
    queryFn: getPoLinkSwitch,
    enabled,
    staleTime: 60_000,
    retry: false,
  });
}
