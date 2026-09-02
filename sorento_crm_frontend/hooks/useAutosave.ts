'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

/** What every committed-change autosave waits before asking the server (D22, S8). */
export const AUTOSAVE_DEBOUNCE_MS = 1000;

export type AutosaveStatus = 'idle' | 'saving' | 'saved' | 'error';

export interface UseAutosaveResult<T> {
  /** What the header reads: `idle` (nothing has changed yet), `saving`
   *  (an edit is queued or in flight), `saved`, or `error`. */
  status: AutosaveStatus;
  /** When the last save actually landed - `null` until the first one has. */
  savedAt: Date | null;
  /** Queue `value` for a debounced save. Call on every committed change. */
  schedule: (value: T) => void;
  /** Save NOW - the debounce's own value if one is pending - and resolve once
   *  everything this hook has in flight has landed. For a moment that cannot
   *  wait out the debounce: a mode switch, a line switch, leaving the page, or
   *  the manual Save button making sure it is not racing an autosave. */
  flush: () => Promise<void>;
  /** Re-send the value a failed save left pending. */
  retry: () => void;
}

/**
 * The one debounce behind every "autosaves on its own" surface (D22, S8).
 *
 * No autosave/debounce precedent existed in the repo for a document editor:
 * the room designer (`RoomDesigner.tsx`) is a manual "Unsaved changes" + Save
 * button, and the only existing debounce (`useDebouncedSearch`) waits on a
 * search box catching up to typing, not on a save landing - it has no status,
 * no flush and no retry, none of which a save can do without. This is a new,
 * small hook rather than a repurposed one, and both dealer-kit hosts that
 * autosave a draft (the request tag designer, the template editor) share it.
 *
 * `schedule` collapses rapid edits into a single save ~1s after the last one -
 * an id of "committed change" needs to be exactly one function, or which
 * edits reset the clock silently drifts apart between the two hosts.
 * `flush` cuts that wait short for a moment that cannot wait for it: it
 * reuses the debounce's OWN pending value, so a mode switch a heartbeat after
 * an edit saves that edit, not whatever was on screen a second earlier. A
 * failed save keeps its value pending - `retry` resends exactly that, not
 * whatever the caller happens to hold by the time someone notices the
 * failure.
 *
 * **Saves are serialised.** Every save chains onto whatever this hook already
 * has in flight rather than racing it (B5). Two overlapping PUTs of the same
 * document can land in either order, and the loser is the one the server keeps
 * - so a flush fired a moment after an autosave could persist the OLDER
 * document and silently undo the newer edit. Chaining also makes `flush`
 * meaningful: it resolves when the work is actually on the server, which is
 * what the page-teardown and manual-Save callers are waiting for.
 */
export function useAutosave<T>(
  onSave: (value: T) => Promise<void>,
  delayMs: number = AUTOSAVE_DEBOUNCE_MS,
): UseAutosaveResult<T> {
  const [status, setStatus] = useState<AutosaveStatus>('idle');
  const [savedAt, setSavedAt] = useState<Date | null>(null);

  // Refs, not state: nothing on screen reads these directly, and status/
  // savedAt above are what re-renders the indicator.
  const pendingValue = useRef<T | null>(null);
  const hasPending = useRef(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inFlight = useRef<Promise<void> | null>(null);
  // Always the latest `onSave` the caller passed, so a save that fires
  // asynchronously - after the caller's own state (e.g. which template id)
  // moved on - still calls the CURRENT closure rather than a stale one
  // captured back when `schedule` was memoized. Assigned in an effect, not
  // during render: a render can be thrown away (Suspense, StrictMode's double
  // pass), and a discarded render must not leave its closure behind as the
  // one a later save will call.
  const onSaveRef = useRef(onSave);
  useEffect(() => {
    onSaveRef.current = onSave;
  }, [onSave]);

  const clearTimer = useCallback(() => {
    if (timer.current !== null) {
      clearTimeout(timer.current);
      timer.current = null;
    }
  }, []);

  /**
   * Actually calls the server, behind whatever is already in flight.
   *
   * Returns the promise the caller should await: the new attempt when there
   * was something to send, the in-flight one when there was not (so a `flush`
   * with nothing pending still waits for a save already on its way), and a
   * resolved promise when this hook is completely idle.
   */
  const runSave = useCallback((): Promise<void> => {
    if (!hasPending.current) return inFlight.current ?? Promise.resolve();
    const value = pendingValue.current as T;
    hasPending.current = false;
    setStatus('saving');
    // The predecessor's own chain swallows its rejection below, so it always
    // settles fulfilled - there is nothing here for a `.catch` to do.
    const previous = inFlight.current ?? Promise.resolve();
    const attempt: Promise<void> = previous
      .then(() => onSaveRef.current(value))
      .then(() => {
        setStatus('saved');
        setSavedAt(new Date());
      })
      .catch(() => {
        // The value stays pending so retry() resends exactly this, not
        // whatever schedule() has been called with since.
        pendingValue.current = value;
        hasPending.current = true;
        setStatus('error');
      })
      .finally(() => {
        // Only if nothing newer has queued behind this one. Clearing
        // unconditionally would drop the pointer to a save that is still
        // running, and the NEXT save would then start in parallel with it -
        // the exact race the chaining above exists to remove.
        if (inFlight.current === attempt) inFlight.current = null;
      });
    inFlight.current = attempt;
    return attempt;
  }, []);

  const schedule = useCallback(
    (value: T) => {
      pendingValue.current = value;
      hasPending.current = true;
      // Optimistic: the reader sees "Saving" the moment an edit lands, not
      // only once the debounce actually fires a request.
      setStatus('saving');
      clearTimer();
      timer.current = setTimeout(() => {
        timer.current = null;
        void runSave();
      }, delayMs);
    },
    [clearTimer, delayMs, runSave],
  );

  const flush = useCallback(async () => {
    clearTimer();
    await runSave();
  }, [clearTimer, runSave]);

  const retry = useCallback(() => {
    if (!hasPending.current) return;
    void runSave();
  }, [runSave]);

  // Nothing left in flight after the host unmounts (a switched line, a
  // closed page) - the callback above already guards `hasPending`, but the
  // TIMER itself has to stop, or a debounce armed a moment before unmount
  // fires a save for a component that is no longer there to hear back from it.
  // Hosts that need the pending EDIT to survive their own unmount call
  // `flush()` in their own cleanup, which runs before this one.
  useEffect(() => clearTimer, [clearTimer]);

  return { status, savedAt, schedule, flush, retry };
}
