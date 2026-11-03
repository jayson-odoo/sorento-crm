'use client';

import * as React from 'react';

import type { TagLayer } from '@/lib/dealer-kit/tag-template-types';

import { useSpecSheetMutations } from '../../../../../../_shared/hooks/useSpecSheet';

/** How long after the last change a page is saved. */
export const AUTOSAVE_MS = 1000;
/** Undo steps kept per page. */
const HISTORY_MAX = 100;

export type SaveStatus = 'idle' | 'saving' | 'saved' | 'error';

interface History {
  stack: TagLayer[][];
  index: number;
}

/**
 * The spec sheet reader's editing state, per page (F4).
 *
 * The live canvases report every change here. Each page keeps its own undo history, saves itself
 * about a second after its last change (one PUT with that page's layers) and survives its canvas
 * unmounting: scrolling a page away does not lose its edits or its undo steps. Nothing refetches;
 * a save writes its answer into the caches instead (`autosavePage`).
 */
export function useSheetEditing(
  projectId: string,
  documentId: string,
  sheetId: string,
) {
  const { autosavePage } = useSpecSheetMutations(projectId, documentId);
  const save = React.useRef(autosavePage.mutateAsync);
  save.current = autosavePage.mutateAsync;

  const drafts = React.useRef(new Map<string, TagLayer[]>());
  const histories = React.useRef(new Map<string, History>());
  const timers = React.useRef(new Map<string, ReturnType<typeof setTimeout>>());
  const chains = React.useRef(new Map<string, Promise<unknown>>());
  const inflight = React.useRef(0);
  const last = React.useRef<string | null>(null);
  // Layers the HOST set (undo, redo): the canvas adopts them.
  const [external, setExternal] = React.useState<Record<string, TagLayer[]>>(
    {},
  );
  const [, bump] = React.useState(0);
  const [status, setStatus] = React.useState<SaveStatus>('idle');

  const flush = React.useCallback(
    (key: string) => {
      timers.current.delete(key);
      const layers = drafts.current.get(key);
      if (!layers) return;
      inflight.current += 1;
      setStatus('saving');
      const run = (chains.current.get(key) ?? Promise.resolve())
        .catch(() => undefined)
        .then(() => save.current({ sheetId, key, layers }));
      chains.current.set(key, run);
      run
        .then(() => {
          inflight.current -= 1;
          if (inflight.current === 0 && timers.current.size === 0)
            setStatus('saved');
        })
        .catch(() => {
          inflight.current -= 1;
          setStatus('error');
        });
    },
    [sheetId],
  );

  const schedule = React.useCallback(
    (key: string) => {
      const pending = timers.current.get(key);
      if (pending) clearTimeout(pending);
      timers.current.set(
        key,
        setTimeout(() => flush(key), AUTOSAVE_MS),
      );
      setStatus('saving');
    },
    [flush],
  );

  // Leaving the reader saves what is still waiting.
  React.useEffect(() => {
    const waiting = timers.current;
    return () => {
      for (const [key, timer] of waiting) {
        clearTimeout(timer);
        flush(key);
      }
    };
  }, [flush]);

  /** A canvas reports the layers it now holds. `base` is what it started from. */
  const report = React.useCallback(
    (key: string, base: TagLayer[], layers: TagLayer[]) => {
      const history = histories.current.get(key) ?? { stack: [base], index: 0 };
      histories.current.set(key, history);
      // The same array again (the canvas echoing what the host gave it, or no change at all).
      if (layers === history.stack[history.index]) return;
      const stack = [
        ...history.stack.slice(0, history.index + 1),
        layers,
      ].slice(-HISTORY_MAX);
      history.stack = stack;
      history.index = stack.length - 1;
      last.current = key;
      drafts.current.set(key, layers);
      bump((n) => n + 1);
      schedule(key);
    },
    [schedule],
  );

  const step = React.useCallback(
    (key: string, delta: -1 | 1) => {
      const history = histories.current.get(key);
      if (!history) return;
      const to = history.index + delta;
      if (to < 0 || to >= history.stack.length) return;
      history.index = to;
      last.current = key;
      const layers = history.stack[to];
      drafts.current.set(key, layers);
      setExternal((prev) => ({ ...prev, [key]: layers }));
      schedule(key);
    },
    [schedule],
  );

  const canUndo = (key: string | null) =>
    Boolean(key && (histories.current.get(key)?.index ?? 0) > 0);
  const canRedo = (key: string | null) => {
    const history = key ? histories.current.get(key) : undefined;
    return Boolean(history && history.index < history.stack.length - 1);
  };

  /** Drop every page's local copy but `keep`'s (the server changed them: apply to every page). */
  const forgetOthers = React.useCallback((keep: string | null) => {
    for (const key of Array.from(drafts.current.keys())) {
      if (key === keep) continue;
      drafts.current.delete(key);
      histories.current.delete(key);
      const timer = timers.current.get(key);
      if (timer) clearTimeout(timer);
      timers.current.delete(key);
    }
    setExternal((prev) => (keep && prev[keep] ? { [keep]: prev[keep] } : {}));
    bump((n) => n + 1);
  }, []);

  return {
    status,
    draftOf: (key: string) => drafts.current.get(key),
    externalOf: (key: string) => external[key],
    report,
    undo: (key: string) => step(key, -1),
    redo: (key: string) => step(key, 1),
    canUndo,
    canRedo,
    lastKey: () => last.current,
    forgetOthers,
  };
}
