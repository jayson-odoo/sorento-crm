import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import {
  getQuickAccessList,
  addQuickAccess,
  removeQuickAccess,
  reorderQuickAccess,
  type QuickAccessItem,
} from '@/lib/quick-access-service';

export const QUICK_ACCESS_QUERY_KEY = ['quick-access'] as const;

export function useQuickAccess() {
  return useQuery({
    queryKey: QUICK_ACCESS_QUERY_KEY,
    queryFn: getQuickAccessList,
    staleTime: 60 * 1000,
  });
}

export function useAddQuickAccess() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ path, label }: { path: string; label?: string | null }) =>
      addQuickAccess(path, label),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUICK_ACCESS_QUERY_KEY });
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to add to quick access'),
  });
}

export function useRemoveQuickAccess() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (entryId: string) => removeQuickAccess(entryId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUICK_ACCESS_QUERY_KEY });
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to remove from quick access'),
  });
}

export function useReorderQuickAccess() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (orderedIds: string[]) => reorderQuickAccess(orderedIds),
    onSuccess: (data) => {
      queryClient.setQueryData(QUICK_ACCESS_QUERY_KEY, data);
    },
    onError: (e: Error) => {
      queryClient.invalidateQueries({ queryKey: QUICK_ACCESS_QUERY_KEY });
      toast.error(e.message || 'Failed to reorder quick access');
    },
  });
}

export type { QuickAccessItem };
