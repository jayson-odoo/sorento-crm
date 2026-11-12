'use client';

import { useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getSnapshot } from '@/services/townService';
import type { TownPayload } from '@/types/town.types';

const POLL_MS = 60_000;

/** The town snapshot, refreshed every minute while the tab is visible (react-query pauses its
 * interval in a hidden tab). The last ETag goes back to the server, and a 304 keeps what we hold. */
export function useTownSnapshot(options?: { mode?: 'wallboard' }) {
  const mode = options?.mode;
  const last = useRef<{ mode?: 'wallboard'; etag?: string; snapshot?: TownPayload }>({});
  const query = useQuery({
    queryKey: ['town-snapshot', mode ?? 'default'],
    queryFn: async () => {
      if (last.current.mode !== mode) last.current = { mode };
      const result = await getSnapshot(last.current.etag, mode);
      if (result.notModified && last.current.snapshot) return last.current.snapshot;
      if (!result.notModified) last.current = { mode, etag: result.etag, snapshot: result.snapshot };
      return last.current.snapshot as TownPayload;
    },
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: false,
  });
  return { snapshot: query.data, error: query.error, isLoading: query.isLoading };
}
