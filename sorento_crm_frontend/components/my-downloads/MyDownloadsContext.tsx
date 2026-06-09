'use client';

/**
 * MyDownloadsContext — drawer open-state + the per-user downloads feed.
 *
 * Server-driven (no optimistic state): the feed is polled every 4s while any
 * row is pending/processing, and forced to refetch when the drawer opens
 * (honours the "no stale data" drawer invariant). The badge counts in-flight +
 * unseen-ready rows.
 */

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { useQuery } from '@tanstack/react-query';

import {
  fetchMyDownloads,
  type MyDownload,
  type MyDownloadsResponse,
} from '@/services/myDownloadsService';

export const MY_DOWNLOADS_QUERY_KEY = ['my-downloads'] as const;

function hasInFlight(rows: MyDownload[]): boolean {
  return rows.some((d) => d.status === 'pending' || d.status === 'processing');
}

interface MyDownloadsApi {
  isOpen: boolean;
  setOpen: (open: boolean) => void;
  downloads: MyDownload[];
  isLoading: boolean;
  badgeCount: number;
  refetch: () => void;
}

const Ctx = createContext<MyDownloadsApi | null>(null);

export function MyDownloadsProvider({ children }: { children: ReactNode }) {
  const [isOpen, setOpen] = useState(false);

  const query = useQuery<MyDownloadsResponse>({
    queryKey: MY_DOWNLOADS_QUERY_KEY,
    queryFn: () => fetchMyDownloads(50),
    refetchInterval: (q) => {
      const rows = (q.state.data as MyDownloadsResponse | undefined)?.downloads;
      return rows && hasInFlight(rows) ? 4_000 : false;
    },
    refetchIntervalInBackground: false,
    staleTime: 0,
  });

  const downloads = useMemo(() => query.data?.downloads ?? [], [query.data]);

  // Badge = in-flight rows (so the user sees something is being prepared).
  const badgeCount = useMemo(
    () => downloads.filter((d) => d.status === 'pending' || d.status === 'processing').length,
    [downloads],
  );

  const refetch = useCallback(() => {
    void query.refetch();
  }, [query]);

  const value = useMemo<MyDownloadsApi>(
    () => ({ isOpen, setOpen, downloads, isLoading: query.isLoading, badgeCount, refetch }),
    [isOpen, downloads, query.isLoading, badgeCount, refetch],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useMyDownloads(): MyDownloadsApi {
  const ctx = useContext(Ctx);
  if (!ctx) {
    throw new Error('useMyDownloads must be used inside <MyDownloadsProvider>');
  }
  return ctx;
}
