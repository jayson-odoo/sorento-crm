'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  createSavedView,
  fetchSavedViews,
  publishSavedView,
  SAVED_VIEWS_QUERY_KEY,
  setDefaultSavedView,
  type SavedView,
  type SavedViewConfig,
  type SavedViews,
} from '@/services/savedViewsService';

/**
 * Saved-view (segment) hooks (S4, PLAN-scm-reorder-oi-feedback-1sep.md). The listing key
 * is a parameter throughout, mirroring `useReports.ts`'s report-key parameterisation -
 * a second listing (AC-4.5) reuses these unchanged.
 */

export function useSavedViews(listingKey: string) {
  return useQuery<SavedViews, Error>({
    queryKey: [SAVED_VIEWS_QUERY_KEY, listingKey],
    queryFn: () => fetchSavedViews(listingKey),
    enabled: Boolean(listingKey),
    staleTime: 60 * 1000,
    retry: 1,
  });
}

export function useSavedViewMutations(listingKey: string) {
  const queryClient = useQueryClient();
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: [SAVED_VIEWS_QUERY_KEY, listingKey] });
  };

  const create = useMutation<SavedView, Error, { name: string; view: SavedViewConfig }>({
    mutationFn: (body) => createSavedView(listingKey, body),
    onSuccess: (view) => {
      invalidate();
      toast.success(`View "${view.name}" saved`);
    },
    onError: (error) => toast.error(error.message || 'Failed to save the view'),
  });

  const publish = useMutation<SavedView, Error, { id: string; isShared: boolean }>({
    mutationFn: ({ id, isShared }) => publishSavedView(id, isShared),
    onSuccess: (view) => {
      invalidate();
      toast.success(view.is_shared ? `"${view.name}" is now shared` : `"${view.name}" is now private`);
    },
    onError: (error) => toast.error(error.message || 'Failed to publish the view'),
  });

  const setDefault = useMutation<SavedView, Error, string>({
    mutationFn: (id) => setDefaultSavedView(id),
    onSuccess: (view) => {
      invalidate();
      toast.success(`"${view.name}" is now the default for everyone`);
    },
    onError: (error) => toast.error(error.message || 'Failed to set the default view'),
  });

  return { create, publish, setDefault };
}
