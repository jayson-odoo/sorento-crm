'use client';

/**
 * useUploadActivity - merged feed of BE sessions + optimistic FE sessions.
 *
 * Phase 2: real BE feed via React Query against
 * GET /api/v1/resources/upload-activity?scope=me. Polled every 5s while any
 * session is in-flight; stops when all terminal. Optimistic sessions from
 * UploadManagerContext layer on top - once the BE returns a session with
 * the same session_id the optimistic copy is dropped via the reducer.
 *
 * Freshness invariants enforced (see feedback_drawer_no_stale_data memory):
 * - drawer-open forces invalidation + refetch (handled by drawer effect)
 * - polling stops as soon as no session is in-flight
 * - new uploads from the dialog force an immediate refetch (Phase 2 wiring)
 */

import { useMemo, useSyncExternalStore } from 'react';
import { useQuery } from '@tanstack/react-query';

import {
  fetchUploadActivity,
  type UploadActivityResponse,
} from '@/services/uploadActivityService';

import {
  dismissKey,
  getDismissedServerSnapshot,
  getDismissedSnapshot,
  subscribeDismissed,
} from './dismissedSessions';
import { UPLOAD_ACTIVITY_QUERY_KEY } from './queryKeys';
import type { UploadActivitySession } from './types';
import { useUploadManager } from './UploadManagerContext';

export interface UploadActivityFeed {
  sessions: UploadActivitySession[];
  badgeCount: number;
  hasInFlight: boolean;
  refetch: () => void;
  isLoading: boolean;
  /** Sessions the user has already seen — excluded from `badgeCount`. */
  dismissed: ReadonlySet<string>;
}

const QUERY_KEY = UPLOAD_ACTIVITY_QUERY_KEY;

function computeBadgeCount(
  sessions: UploadActivitySession[],
  dismissed: ReadonlySet<string>,
): number {
  let count = 0;
  for (const s of sessions) {
    // Dismissed in the state it is still in — silent. The key carries the state,
    // so a session that CHANGES (a stuck upload that finally fails) no longer
    // matches its old entry and starts counting again on its own.
    if (dismissed.has(dismissKey(s))) continue;
    if (s.status === 'uploading' || s.status === 'processing') {
      count += 1;
      continue;
    }
    if (s.needs_action) count += 1;
  }
  return count;
}

function computeHasInFlight(sessions: UploadActivitySession[]): boolean {
  return sessions.some(
    (s) => s.status === 'uploading' || s.status === 'processing',
  );
}

export function useUploadActivity(): UploadActivityFeed {
  const { state } = useUploadManager();

  // Initial fetch + poll while in-flight. Optimistic sessions decide the
  // polling cadence even before the first BE response arrives.
  const optimisticInFlight = useMemo(
    () => computeHasInFlight(Object.values(state.sessions)),
    [state.sessions],
  );

  const query = useQuery<UploadActivityResponse>({
    queryKey: QUERY_KEY,
    queryFn: () => fetchUploadActivity({ scope: 'me' }),
    // refetchInterval reads from latest data via callback form so we can
    // observe BE-side in-flight too, not just optimistic.
    refetchInterval: (q) => {
      const latest = (q.state.data as UploadActivityResponse | undefined)
        ?.sessions;
      const beInFlight = latest ? computeHasInFlight(latest) : false;
      return optimisticInFlight || beInFlight ? 5_000 : false;
    },
    refetchIntervalInBackground: false,
    // Stale immediately so refetch on drawer-open (handled in
    // UploadActivityDrawer's effect) hits the network.
    staleTime: 0,
  });

  // Seen-set lives outside React (localStorage), so the badge has to subscribe
  // to it rather than read it once — the drawer marks sessions seen on open and
  // the badge must drop in the same commit.
  const dismissedIds = useSyncExternalStore(
    subscribeDismissed,
    getDismissedSnapshot,
    getDismissedServerSnapshot,
  );
  const dismissed = useMemo(() => new Set(dismissedIds), [dismissedIds]);

  const sessions = useMemo<UploadActivitySession[]>(() => {
    const beList = query.data?.sessions ?? [];
    const optimistic = Object.values(state.sessions);
    // Optimistic sessions show until BE has them. BE wins on session_id conflict.
    const byId = new Map<string, UploadActivitySession>();
    for (const s of optimistic) byId.set(s.session_id, s);
    for (const s of beList) byId.set(s.session_id, s);
    return Array.from(byId.values()).sort(
      (a, b) =>
        new Date(b.started_at).getTime() - new Date(a.started_at).getTime(),
    );
  }, [query.data, state.sessions]);

  return {
    sessions,
    badgeCount: computeBadgeCount(sessions, dismissed),
    hasInFlight: computeHasInFlight(sessions),
    refetch: () => {
      void query.refetch();
    },
    isLoading: query.isLoading,
    dismissed,
  };
}

// `UPLOAD_ACTIVITY_QUERY_KEY` lives in `./queryKeys` to avoid a cycle with
// UploadManagerContext; re-exported from `index.ts` for callers that need it.
