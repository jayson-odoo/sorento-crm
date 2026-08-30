'use client';

import {
  useMutation,
  useQueryClient,
  type QueryKey,
  type UseMutationResult,
} from '@tanstack/react-query';
import { toast } from 'sonner';

/**
 * One write against one row, applied to the cache before the server answers (S7-01).
 *
 * The shape this replaces was the same six lines in every list that carries a
 * switch: `mutationFn`, `invalidateQueries` on success, a toast, and
 * `disabled={mut.isPending}` on the control. That last one is what the reader
 * feels - the switch does not move until the round trip lands and the list
 * refetches, so a toggle reads as broken on a slow connection and gets pressed
 * twice.
 *
 * So the factory does the three things a hand-rolled `onMutate` has to get right
 * and usually does not: cancel the in-flight reads that would overwrite the
 * patch, snapshot every cached entry it touches so a failure can put the old
 * value back, and invalidate once the dust settles. Everything specific to a
 * feature stays with the feature: which key holds the rows, which row this is,
 * and which fields change.
 *
 * Not a general-purpose cache editor. It knows the two shapes this codebase
 * actually caches - a bare `Row[]` and a `{ data: Row[] }` list envelope - plus
 * the single record a detail query holds. A cache shaped some other way is left
 * untouched and the invalidation still corrects it; nothing is guessed.
 */

/** A cached row is any object; the caller's `matchRow` is what gives it meaning. */
type CachedRow = Record<string, unknown>;

export interface EntityMutationInput<TVars, TData> {
  /** The service call. Same function the non-optimistic hook passed to `useMutation`. */
  mutationFn: (vars: TVars) => Promise<TData>;
  /**
   * Query key PREFIXES holding the row this write changes. Every cached entry
   * under each prefix is patched, and every one of them is invalidated on settle.
   */
  keys: readonly QueryKey[];
  /** Is this cached row the one the write is about? */
  matchRow: (row: CachedRow, variables: TVars) => boolean;
  /** The fields that change, merged into the matched row. */
  patchRow: (variables: TVars) => CachedRow;
  /** Said once the server has applied it. Return null to say nothing. */
  successMessage?: (data: TData, variables: TVars) => string | null;
  /** Prefix for the rollback toast; the server's message follows it. */
  errorMessage?: string;
  onSuccess?: (data: TData, variables: TVars) => void;
}

function patchCachedValue(
  cached: unknown,
  isTarget: (row: CachedRow) => boolean,
  patch: CachedRow,
): unknown {
  if (Array.isArray(cached)) {
    let changed = false;
    const next = cached.map((entry) => {
      if (entry && typeof entry === 'object' && isTarget(entry as CachedRow)) {
        changed = true;
        return { ...(entry as CachedRow), ...patch };
      }
      return entry;
    });
    return changed ? next : cached;
  }

  if (cached && typeof cached === 'object') {
    const envelope = cached as CachedRow;
    if (Array.isArray(envelope.data)) {
      const nextData = patchCachedValue(envelope.data, isTarget, patch);
      return nextData === envelope.data ? cached : { ...envelope, data: nextData };
    }
    if (isTarget(envelope)) {
      return { ...envelope, ...patch };
    }
  }

  return cached;
}

export function useEntityMutation<TVars, TData>(
  input: EntityMutationInput<TVars, TData>,
): UseMutationResult<TData, Error, TVars, readonly [QueryKey, unknown][]> {
  const queryClient = useQueryClient();
  const { mutationFn, keys, matchRow, patchRow, successMessage, errorMessage, onSuccess } = input;

  return useMutation<TData, Error, TVars, readonly [QueryKey, unknown][]>({
    mutationFn,

    // The optimistic half. `onMutate`'s return value is the rollback.
    onMutate: async (variables) => {
      const isTarget = (row: CachedRow) => matchRow(row, variables);
      const patch = patchRow(variables);
      const snapshot: [QueryKey, unknown][] = [];

      for (const key of keys) {
        // A read already in flight would land after the patch and undo it.
        await queryClient.cancelQueries({ queryKey: key });
        for (const [queryKey, cached] of queryClient.getQueriesData({ queryKey: key })) {
          const next = patchCachedValue(cached, isTarget, patch);
          if (next === cached) continue;
          snapshot.push([queryKey, cached]);
          queryClient.setQueryData(queryKey, next);
        }
      }

      return snapshot;
    },

    onError: (error, _variables, snapshot) => {
      for (const [queryKey, cached] of snapshot ?? []) {
        queryClient.setQueryData(queryKey, cached);
      }
      const detail = error?.message?.trim();
      toast.error(
        errorMessage && detail
          ? `${errorMessage}: ${detail}`
          : errorMessage || detail || 'Something went wrong.',
      );
    },

    onSuccess: (data, variables) => {
      const message = successMessage?.(data, variables);
      if (message) toast.success(message);
      onSuccess?.(data, variables);
    },

    // Settle, not success: a rolled-back cache is as stale as a patched one.
    onSettled: () => {
      for (const key of keys) {
        void queryClient.invalidateQueries({ queryKey: key });
      }
    },
  });
}
