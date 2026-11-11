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
  /**
   * The array the last undo / redo handed the canvas: a fresh copy of `stack[index]`, because the
   * canvas adopts host layers only when the array is a new one (undo, edit, undo to the same step
   * twice otherwise never reached the screen). The canvas echoing it back is no edit. The stack
   * itself keeps its own arrays, so a canvas that remounts from the payload still matches it.
   */
  handed?: TagLayer[];
}

/**
 * The spec sheet reader's editing state, per page (F4).
 *
 * The live canvases report every change here. Each page keeps its own undo history, saves itself
 * about a second after its last change (one PUT with that page's layers) and survives its canvas
 * unmounting: scrolling a page away does not lose its edits or its undo steps. Nothing refetches;
 * a save writes its answer into the caches instead (`autosavePage`).
 *
 * Save state is per page: a page whose save failed stays "failed" (and is tried again with the
 * next flush) however many other pages save, and the sheet reads "Saved" only when none is left.
 * While anything is waiting or in flight the tab asks before it closes.
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
  const failed = React.useRef(new Set<string>());
  const inflight = React.useRef(0);
  const last = React.useRef<string | null>(null);
  // Saves wait here while "Apply to every page" is running, so none lands in the middle of it.
  const gate = React.useRef<Promise<void>>(Promise.resolve());
  // Layers the HOST set (undo, redo): the canvas adopts them.
  const [external, setExternal] = React.useState<Record<string, TagLayer[]>>(
    {},
  );
  const [, bump] = React.useState(0);
  const [status, setStatus] = React.useState<SaveStatus>('idle');
  const [busy, setBusy] = React.useState(false);

  /** Re-derive the sheet's mark and the unload guard from what is waiting, running and failed. */
  const refresh = React.useCallback(() => {
    const working = timers.current.size > 0 || inflight.current > 0;
    setBusy(working);
    setStatus((prev) => {
      if (failed.current.size > 0 && !working) return 'error';
      if (working) return 'saving';
      return prev === 'idle' ? 'idle' : 'saved';
    });
  }, []);

  const send = React.useCallback(
    (key: string): Promise<unknown> | null => {
      const layers = drafts.current.get(key);
      if (!layers) return null;
      inflight.current += 1;
      const run = (chains.current.get(key) ?? Promise.resolve())
        .catch(() => undefined)
        .then(() => gate.current)
        .then(() => save.current({ sheetId, key, layers }));
      chains.current.set(key, run);
      const done = run
        .then(() => {
          failed.current.delete(key);
        })
        .catch(() => {
          failed.current.add(key);
        })
        .finally(() => {
          inflight.current -= 1;
          refresh();
        });
      refresh();
      return done;
    },
    [sheetId, refresh],
  );

  const flush = React.useCallback(
    (key: string) => {
      timers.current.delete(key);
      send(key);
      // A page whose last save failed is tried again with the next one.
      for (const other of Array.from(failed.current)) {
        if (other !== key && !timers.current.has(other)) send(other);
      }
    },
    [send],
  );

  const schedule = React.useCallback(
    (key: string) => {
      const pending = timers.current.get(key);
      if (pending) clearTimeout(pending);
      timers.current.set(
        key,
        setTimeout(() => flush(key), AUTOSAVE_MS),
      );
      refresh();
    },
    [flush, refresh],
  );

  /**
   * Send every page that is waiting and wait for every save in flight, then hold new saves back
   * until `release` is called. "Apply to every page" runs between the two, so it never overtakes
   * (or is overtaken by) another page's edit.
   */
  const settle = React.useCallback(async (): Promise<() => void> => {
    for (const [key, timer] of Array.from(timers.current)) {
      clearTimeout(timer);
      timers.current.delete(key);
      send(key);
    }
    // Wait for what was just sent (and anything already in flight) BEFORE closing the gate: the
    // saves queue behind the gate they are created under.
    await Promise.all(
      Array.from(chains.current.values()).map((c) => c.catch(() => undefined)),
    );
    let release: () => void = () => undefined;
    gate.current = new Promise<void>((resolve) => {
      release = resolve;
    });
    return release;
  }, [send]);

  // Leaving the reader saves what is still waiting.
  React.useEffect(() => {
    const waiting = timers.current;
    return () => {
      for (const [key, timer] of waiting) {
        clearTimeout(timer);
        send(key);
      }
    };
  }, [send]);

  // The tab asks before it closes while a save is waiting or running.
  React.useEffect(() => {
    if (!busy) return;
    const guard = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', guard);
    return () => window.removeEventListener('beforeunload', guard);
  }, [busy]);

  /** A canvas reports the layers it now holds. `base` is what it started from. */
  const report = React.useCallback(
    (key: string, base: TagLayer[], layers: TagLayer[]) => {
      const prior = histories.current.get(key);
      // A canvas that started over from a document this page's history does not hold (the sheet
      // switched templates, so the page is drawn again from the server) echoes that document
      // first. It is the page's new starting point, not an edit: nothing is saved, and the old
      // template's undo steps go.
      if (
        prior &&
        layers === base &&
        layers !== prior.stack[prior.index] &&
        layers !== prior.handed
      ) {
        histories.current.set(key, { stack: [base], index: 0 });
        drafts.current.delete(key);
        bump((n) => n + 1);
        return;
      }
      const history = prior ?? { stack: [base], index: 0 };
      histories.current.set(key, history);
      // The same array again (the canvas echoing what the host gave it, or no change at all).
      if (layers === history.stack[history.index] || layers === history.handed) return;
      history.handed = undefined;
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
      // A fresh array every step (see `History.handed`), remembered so its echo is no edit.
      const layers = [...history.stack[to]];
      history.handed = layers;
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

  /**
   * Drop the local copy of every page but `keep`'s (the server changed them: apply to every page).
   * A page with an edit not yet sent, or whose save failed, keeps its copy: it was never sent.
   */
  const forgetOthers = React.useCallback((keep: string | null) => {
    for (const key of Array.from(drafts.current.keys())) {
      if (key === keep || timers.current.has(key) || failed.current.has(key))
        continue;
      drafts.current.delete(key);
      histories.current.delete(key);
    }
    setExternal((prev) => {
      const next: Record<string, TagLayer[]> = {};
      for (const [key, layers] of Object.entries(prev)) {
        if (key === keep || drafts.current.has(key)) next[key] = layers;
      }
      return next;
    });
    bump((n) => n + 1);
  }, []);

  /**
   * Drop everything this page holds locally: its draft, undo history, host-set layers and the save
   * that was waiting ("Reset to template": the server dropped the override, so the old layers
   * must not be saved back by the next edit).
   */
  const forget = React.useCallback(
    (key: string) => {
      const pending = timers.current.get(key);
      if (pending) clearTimeout(pending);
      timers.current.delete(key);
      drafts.current.delete(key);
      histories.current.delete(key);
      failed.current.delete(key);
      setExternal((prev) => {
        if (!(key in prev)) return prev;
        const next = { ...prev };
        delete next[key];
        return next;
      });
      bump((n) => n + 1);
      refresh();
    },
    [refresh],
  );

  return {
    status,
    forget,
    draftOf: (key: string) => drafts.current.get(key),
    externalOf: (key: string) => external[key],
    report,
    undo: (key: string) => step(key, -1),
    redo: (key: string) => step(key, 1),
    canUndo,
    canRedo,
    lastKey: () => last.current,
    forgetOthers,
    settle,
  };
}
