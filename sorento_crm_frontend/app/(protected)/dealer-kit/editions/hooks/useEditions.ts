'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import {
  approveEdition,
  createEdition,
  getEdition,
  listEditions,
  publishEdition,
  reopenEdition,
  rejectEdition,
  submitEdition,
  type Edition,
} from '../../services/editionService';

export const EDITIONS_QUERY_KEY = 'dealer-kit-editions';

export function useEditionsQuery(pageId?: string) {
  return useQuery({
    queryKey: [EDITIONS_QUERY_KEY, pageId ?? 'all'],
    queryFn: () => listEditions(pageId),
  });
}

export function useEditionQuery(editionId: string) {
  return useQuery({
    queryKey: [EDITIONS_QUERY_KEY, 'detail', editionId],
    queryFn: () => getEdition(editionId),
    enabled: Boolean(editionId),
  });
}

/**
 * Every transition shares this shape, so they share one hook.
 *
 * The list AND the detail are invalidated on success. A transition changes both
 * - the queue a reviewer is working from and the record in front of them - and
 * invalidating only the detail leaves an approved Edition still sitting in the
 * pending queue behind it.
 */
function useTransition(
  editionId: string,
  action: (id: string) => Promise<Edition>,
  successMessage: (edition: Edition) => string,
) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => action(editionId),
    onSuccess: (edition) => {
      queryClient.invalidateQueries({ queryKey: [EDITIONS_QUERY_KEY] });
      // The page's own version list changes when an Edition publishes, and the
      // editor may be open behind this.
      queryClient.invalidateQueries({ queryKey: ['dealer-kit', 'page', edition.pageId] });
      queryClient.invalidateQueries({ queryKey: ['dealer-kit', 'pages'] });
      toast.success(successMessage(edition));
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

export const useSubmitEdition = (id: string) =>
  useTransition(id, submitEdition, () => 'Sent for approval');

export const useApproveEdition = (id: string) =>
  useTransition(id, approveEdition, () => 'Approved. It is not live until you publish it.');

export const useReopenEdition = (id: string) =>
  useTransition(id, reopenEdition, () => 'Reopened for editing');

export const usePublishEdition = (id: string) =>
  useTransition(id, publishEdition, () => 'Published');

export function useRejectEdition(editionId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (reason: string) => rejectEdition(editionId, reason),
    onSuccess: (edition) => {
      queryClient.invalidateQueries({ queryKey: [EDITIONS_QUERY_KEY] });
      queryClient.invalidateQueries({ queryKey: ['dealer-kit', 'page', edition.pageId] });
      toast.success('Rejected. The designer will see your reason.');
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

export function useCreateEdition() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: createEdition,
    onSuccess: (edition) => {
      queryClient.invalidateQueries({ queryKey: [EDITIONS_QUERY_KEY] });
      toast.success(`${edition.name} started`);
    },
    onError: (error: Error) => toast.error(error.message),
  });
}
