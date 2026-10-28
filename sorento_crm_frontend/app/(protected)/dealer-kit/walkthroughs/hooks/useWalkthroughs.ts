'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';

import {
  addStop,
  createWalkthrough,
  getPanorama,
  getWalkthrough,
  listWalkthroughs,
  renameWalkthrough,
  type Walkthrough,
  type WalkthroughStop,
} from '../../services/walkthroughService';

export const WALKTHROUGHS_QUERY_KEY = 'dealer-kit-walkthroughs';

/** How often a stop that is still being stitched is asked about again. */
const PROCESSING_POLL_MS = 3000;

/** Polls only while a stop is still being built, like the flyer list. */
export function useWalkthroughsQuery() {
  return useQuery({
    queryKey: [WALKTHROUGHS_QUERY_KEY],
    queryFn: listWalkthroughs,
    refetchInterval: (query) =>
      (query.state.data ?? []).some((row) => row.processingCount > 0) ? PROCESSING_POLL_MS : false,
    retry: 1,
  });
}

export function useWalkthroughQuery(id: string) {
  return useQuery({
    queryKey: [WALKTHROUGHS_QUERY_KEY, id],
    queryFn: () => getWalkthrough(id),
    enabled: Boolean(id),
    refetchInterval: (query) =>
      query.state.data?.stops.some((stop) => stop.status === 'processing')
        ? PROCESSING_POLL_MS
        : false,
    retry: 1,
  });
}

/** The panorama bytes. A finished stop never changes, so it is cached for good. */
export function usePanoramaQuery(id: string, stop: WalkthroughStop | null) {
  return useQuery({
    queryKey: [WALKTHROUGHS_QUERY_KEY, id, 'panorama', stop?.id ?? ''],
    queryFn: () => getPanorama(id, stop!.id),
    enabled: Boolean(stop && stop.status === 'done'),
    staleTime: Infinity,
    retry: 1,
  });
}

export function useCreateWalkthrough() {
  const queryClient = useQueryClient();
  return useMutation<Walkthrough, Error, string>({
    mutationFn: createWalkthrough,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [WALKTHROUGHS_QUERY_KEY] });
      toast.success('Walkthrough created');
    },
    onError: (error) => toast.error(error.message || 'Could not create the walkthrough'),
  });
}

export function useRenameWalkthrough(id: string) {
  const queryClient = useQueryClient();
  return useMutation<Walkthrough, Error, string>({
    mutationFn: (name) => renameWalkthrough(id, name),
    onSuccess: (walkthrough) => {
      queryClient.setQueryData([WALKTHROUGHS_QUERY_KEY, id], walkthrough);
      queryClient.invalidateQueries({ queryKey: [WALKTHROUGHS_QUERY_KEY], exact: true });
      toast.success('Walkthrough renamed');
    },
    onError: (error) => toast.error(error.message || 'Could not rename the walkthrough'),
  });
}

/**
 * A 202 can carry a stop already `failed` (the queue was down), so the row,
 * not the status code, decides which toast is shown.
 */
export function useAddStop(id: string) {
  const queryClient = useQueryClient();
  return useMutation<WalkthroughStop, Error, { files: File[]; title: string }>({
    mutationFn: ({ files, title }) => addStop(id, files, title),
    onSuccess: (stop) => {
      queryClient.invalidateQueries({ queryKey: [WALKTHROUGHS_QUERY_KEY] });
      if (stop.status === 'failed') {
        toast.error(stop.errorMessage || 'Could not build this stop');
        return;
      }
      toast.success('Building the stop in the background');
    },
    onError: (error) => toast.error(error.message || 'Could not add this stop'),
  });
}
