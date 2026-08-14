'use client';

import { useCallback, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  createMarketTopic,
  deleteMarketTopic,
  listMarketSignals,
  listMarketTopics,
  runMarketResearch,
  updateMarketTopic,
} from '../services/marketService';
import type { MarketResearchRun, MarketResearchTopicWrite } from '../types/market.types';

const SIGNALS_KEY = ['scm', 'market', 'signals'] as const;
const TOPICS_KEY = ['scm', 'market', 'topics'] as const;

// ── Signals (read-only viz) ──────────────────────────────────────────────────

export function useMarketSignals() {
  return useQuery({
    queryKey: SIGNALS_KEY,
    queryFn: listMarketSignals,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

// ── Topics ───────────────────────────────────────────────────────────────────

export function useMarketTopics() {
  return useQuery({
    queryKey: TOPICS_KEY,
    queryFn: listMarketTopics,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useCreateTopic() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: MarketResearchTopicWrite) => createMarketTopic(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: TOPICS_KEY });
      toast.success('Research topic created');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useUpdateTopic() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: MarketResearchTopicWrite }) =>
      updateMarketTopic(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: TOPICS_KEY });
      toast.success('Research topic updated');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useDeleteTopic() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteMarketTopic(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: TOPICS_KEY });
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

// ── Run research ─────────────────────────────────────────────────────────────

export interface RunResearchController {
  /** null before the first run of this session. */
  run: MarketResearchRun | null;
  isRunning: boolean;
  isComplete: boolean;
  isFailed: boolean;
  error: string | null;
  /** Fire a run. Refreshes signals on success + toasts with the fresh-signal count. */
  start: () => Promise<void>;
  /** Dismiss the completed/failed feedback card. */
  reset: () => void;
}

/**
 * Trigger a market-research run and expose a stable running→complete controller
 * (mirrors the reorder-run feedback shape). On success it invalidates the signals
 * query so the freshly-captured signals appear, and toasts the new-signal count.
 */
export function useRunResearch(): RunResearchController {
  const qc = useQueryClient();
  const [run, setRun] = useState<MarketResearchRun | null>(null);
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () => runMarketResearch(),
    onSuccess: (result) => {
      setRun(result);
      setError(null);
      void qc.invalidateQueries({ queryKey: SIGNALS_KEY });
      const n = result.signal_count;
      toast.success(
        n > 0
          ? `Research complete - ${n} new market signal${n === 1 ? '' : 's'} captured`
          : 'Research complete - no new signals this run',
      );
    },
    onError: (e: Error) => {
      setError(e.message);
      setRun({
        id: '',
        status: 'failed',
        started_at: '',
        finished_at: null,
        topic_count: 0,
        signal_count: 0,
        error: e.message,
      });
      toast.error(e.message);
    },
  });

  const start = useCallback(async () => {
    setError(null);
    setRun(null);
    await mutation.mutateAsync().catch(() => {
      /* error surfaced via onError + the failed run record */
    });
  }, [mutation]);

  const reset = useCallback(() => {
    setRun(null);
    setError(null);
  }, []);

  return {
    run,
    isRunning: mutation.isPending,
    isComplete: !mutation.isPending && run?.status === 'completed',
    isFailed: !mutation.isPending && (run?.status === 'failed' || !!error),
    error: error ?? run?.error ?? null,
    start,
    reset,
  };
}
