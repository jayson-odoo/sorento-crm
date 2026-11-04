'use client';

import { useQuery } from '@tanstack/react-query';
import {
  DEFAULT_DEFERRED_DELETE_SECONDS,
  getDeferredDeleteSeconds,
} from '@/services/deferredWindowService';

/**
 * The hard-delete countdown in seconds, for a countdown the browser runs itself (a quotation
 * column removal). The default while loading or when the setting cannot be read.
 */
export function useDeferredDeleteSeconds(): number {
  const { data } = useQuery({
    queryKey: ['system-app-config', 'deferred-delete-seconds'],
    queryFn: getDeferredDeleteSeconds,
    staleTime: Infinity,
    refetchOnReconnect: false,
    retry: false,
  });
  return data ?? DEFAULT_DEFERRED_DELETE_SECONDS;
}
