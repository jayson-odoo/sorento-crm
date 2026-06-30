import { useCallback, useRef, useState } from 'react';

/**
 * Reusable guard for one-shot mutating action buttons (approve, set-pending, send…).
 *
 * Stops the duplicate-submit class of bug at the UI:
 *  - Synchronous `useRef` in-flight lock: React state does not disable the DOM button
 *    until the next render, so a same-tick double-click would fire two handlers. The
 *    ref blocks the 2nd immediately.
 *  - `running` flag for `disabled` / label.
 *
 * IMPORTANT: keep the dependent refetch INSIDE `fn` and `await` it, e.g.
 *   const setPending = useAction(async () => {
 *     await setPendingApproval(id);
 *     await queryClient.invalidateQueries({ queryKey: ['purchase-request', id] });
 *   });
 * Awaiting the invalidate keeps `running` true until the entity reflects the change,
 * so the button stays disabled instead of re-enabling on a stale view (the other half
 * of the duplicate-submit window). The backend idempotency middleware is the server
 * backstop for anything the UI misses (proxy retries, scripts, two tabs).
 */
export function useAction<TArgs extends unknown[], TResult>(
  fn: (...args: TArgs) => Promise<TResult>,
) {
  const [running, setRunning] = useState(false);
  const lock = useRef(false);

  const run = useCallback(
    async (...args: TArgs): Promise<TResult | undefined> => {
      if (lock.current) return undefined; // ignore same-tick / re-entrant clicks
      lock.current = true;
      setRunning(true);
      try {
        return await fn(...args);
      } finally {
        lock.current = false;
        setRunning(false);
      }
    },
    [fn],
  );

  return { run, running };
}
