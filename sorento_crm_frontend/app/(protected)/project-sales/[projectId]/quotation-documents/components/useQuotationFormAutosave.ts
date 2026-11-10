'use client';

import * as React from 'react';
import { useAutosave, type AutosaveStatus } from '@/hooks/useAutosave';
import {
  DraftNotHolderError,
  getQuotationDraftHolder,
  saveQuotationFormDraft,
  type QuotationFormState,
} from '../../../_shared/services/quotationDocumentService';

/**
 * QUOTE-AUTOSAVE: the proposal / quotation form's autosave (plan
 * `documentation/plans/project-sales/PLAN-quote-autosave-10nov.md`; owner's answers of 10 Nov).
 *
 * The tag designer's own debounce (`hooks/useAutosave`: 1 s after the last change, saves
 * serialised, `flush`, `retry`) writing the DRAFT, never the record:
 *
 * - **A new proposal** (Q2) writes the person's own private draft; nothing is numbered until Save.
 * - **Every edit** is mirrored to this browser's local storage until the server has it, so a tab
 *   closed while offline still comes back on the next open (`readMirrors`). One copy per TAB
 *   (keyed by its claim), and each remembers which server version it was made on (`baseAt`), so
 *   an older tab cannot overwrite the holder's copy and a copy the server has moved past (a Save,
 *   a Discard, another tab) is never reopened as if it were newer.
 * - **Leaving** flushes: an in-app route change unmounts the form, a refresh or a closed tab fires
 *   `pagehide` (sent `keepalive`, so it outlives the page): the request designer's two exits
 *   (`RequestTagDesigner.tsx:1110-1136`).
 * - **Back online** retries the failed save on its own.
 * - **Two tabs** (Q4): the form claims the draft when it opens (`token`). A tab another open took
 *   the draft from is refused (409), and finds out within `HOLDER_POLL_MS` even when idle; it then
 *   goes view-only (`viewOnly`), and what it had not sent is kept by the server as History.
 * - **Discard draft** pauses saving while its 5 s countdown runs, so nothing written during the
 *   countdown, or by the unmount that follows it, brings the discarded draft back.
 */

/** How often an idle tab asks whether it still holds the draft. */
export const HOLDER_POLL_MS = 15_000;

export type MirroredDraft = {
  token: string | null;
  /** The server draft's `updated_at` this copy was made on top of (null: none yet). */
  baseAt: string | null;
  doc: QuotationFormState;
  at: string;
};

/** Every tab's copy of one draft starts with this. */
export function mirrorPrefix(projectId: string, documentId: string | null): string {
  return documentId
    ? `quotation-form-draft:${documentId}:`
    : `quotation-form-draft:new:${projectId}:`;
}

/** This tab's own copy: per claim, so two tabs never write over each other's. */
export function mirrorKey(projectId: string, documentId: string | null, token: string | null): string {
  return `${mirrorPrefix(projectId, documentId)}${token ?? 'none'}`;
}

/** Every tab's copy of one draft this browser holds, oldest first. */
export function readMirrors(prefix: string): { key: string; value: MirroredDraft }[] {
  const out: { key: string; value: MirroredDraft }[] = [];
  try {
    for (let index = 0; index < window.localStorage.length; index += 1) {
      const key = window.localStorage.key(index);
      if (!key || !key.startsWith(prefix)) continue;
      const value = readMirror(key);
      if (value) out.push({ key, value });
    }
  } catch {
    // Storage blocked: there is nothing to reopen.
  }
  return out.sort((a, b) => a.value.at.localeCompare(b.value.at));
}

/** The unsent copy this browser holds, or null. Storage can throw (private mode): never fatal. */
export function readMirror(key: string): MirroredDraft | null {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as MirroredDraft;
    return parsed && typeof parsed === 'object' && parsed.doc ? parsed : null;
  } catch {
    return null;
  }
}

export function writeMirror(key: string, value: MirroredDraft): void {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // A full or blocked store only loses the offline safety net, never the server save.
  }
}

export function clearMirror(key: string): void {
  try {
    window.localStorage.removeItem(key);
  } catch {
    // As above.
  }
}

export type DraftViewOnly = { holderName: string | null; holderAt: string | null };

export type UseQuotationFormAutosave = {
  status: AutosaveStatus;
  savedAt: Date | null;
  retry: () => void;
  flush: () => Promise<void>;
  /** Another tab or person opened the draft after this tab: fields lock, Save is off. */
  viewOnly: DraftViewOnly | null;
  /** Save `state` as soon as the debounce allows: an unsent local copy the form reopened on. */
  resume: (state: QuotationFormState) => void;
  /** Stop (true) or restart (false) saving: the Discard draft countdown. */
  setPaused: (paused: boolean) => void;
  /** Lock the form as view-only now (a refused Save or Restore said the draft moved on). */
  lockOut: (holderName: string | null, holderAt: string | null) => void;
  /** Ask the server now whether this tab still holds the draft (after a refused Save). */
  checkNow: () => Promise<void>;
  /** Drop this tab's local copy: Discard draft has started. */
  forgetLocalCopy: () => void;
};

export function useQuotationFormAutosave({
  projectId,
  documentId,
  token,
  baseAt,
  state,
  isDirty,
  ready,
}: {
  projectId: string;
  /** The document, or null for a new proposal's private draft. */
  documentId: string | null;
  /** This tab's claim on the draft, from opening it; null until it has opened. */
  token: string | null;
  /** The server draft's `updated_at` when this tab opened it. */
  baseAt: string | null;
  /** The form's state, or null until the form has its starting point. */
  state: QuotationFormState | null;
  /** Something has been typed: before that, a changing state is the form loading, not an edit. */
  isDirty: boolean;
  /** The form has opened its draft and may save (false while loading or locked). */
  ready: boolean;
}): UseQuotationFormAutosave {
  const [viewOnly, setViewOnly] = React.useState<DraftViewOnly | null>(null);
  const viewOnlyRef = React.useRef(false);
  const pausedRef = React.useRef(false);
  const teardownRef = React.useRef(false);
  const tokenRef = React.useRef(token);
  const documentIdRef = React.useRef(documentId);
  /** The server draft's version this tab last saw: its own saves move it. */
  const serverAtRef = React.useRef<string | null>(baseAt);
  React.useEffect(() => {
    tokenRef.current = token;
    documentIdRef.current = documentId;
  }, [token, documentId]);
  React.useEffect(() => {
    serverAtRef.current = baseAt;
  }, [baseAt]);

  const lockOut = React.useCallback((holderName: string | null, holderAt: string | null) => {
    viewOnlyRef.current = true;
    setViewOnly({ holderName, holderAt });
  }, []);

  const { status, savedAt, schedule, flush, retry } = useAutosave<QuotationFormState>(
    React.useCallback(
      async (value: QuotationFormState) => {
        if (pausedRef.current) return;
        const key = mirrorKey(projectId, documentIdRef.current, tokenRef.current);
        try {
          const saved = await saveQuotationFormDraft(
            projectId,
            documentIdRef.current,
            value,
            tokenRef.current ?? '',
            { keepalive: teardownRef.current },
          );
          serverAtRef.current = saved?.updated_at ?? serverAtRef.current;
          // The copy may already hold a NEWER edit typed while this one was on its way: keep that
          // and move its base to the version just written, or a reopen would read it as stale
          // (review 5/7a). Only the copy of exactly what landed is dropped.
          const copy = readMirror(key);
          if (copy && JSON.stringify(copy.doc) !== JSON.stringify(value)) {
            writeMirror(key, { ...copy, baseAt: serverAtRef.current });
          } else {
            clearMirror(key);
          }
        } catch (error) {
          if (error instanceof DraftNotHolderError) {
            // The server kept this tab's state as History; the local copy is not needed.
            clearMirror(key);
            lockOut(error.holderName, error.holderAt);
            return;
          }
          throw error;
        }
      },
      [projectId, lockOut],
    ),
  );

  // Every REAL edit schedules a save. Guarded on the serialised VALUE, not a "have I run" flag: the
  // first value is the form's starting point and only moves the baseline, and so does any change
  // made before anything was typed (a template default, a scope opened and seeded from the
  // server). The live total is left out: opening a saved scope re-sums it, the same money written
  // differently, and that is not an edit. Comparing values also makes StrictMode's double effect
  // pass a no-op.
  const lastSeen = React.useRef<string | undefined>(undefined);
  React.useEffect(() => {
    if (!ready || state === null) return;
    const json = JSON.stringify({ ...state, total: undefined });
    if (json === lastSeen.current) return;
    const isInitial = lastSeen.current === undefined;
    lastSeen.current = json;
    if (isInitial || !isDirty || viewOnlyRef.current || pausedRef.current) return;
    writeMirror(mirrorKey(projectId, documentIdRef.current, tokenRef.current), {
      token: tokenRef.current,
      baseAt: serverAtRef.current,
      doc: state,
      at: new Date().toISOString(),
    });
    schedule(state);
  }, [state, isDirty, ready, schedule, projectId]);

  // Leaving the page, both ways it can happen.
  React.useEffect(() => {
    teardownRef.current = false;
    const handler = () => {
      teardownRef.current = true;
      void flush();
    };
    window.addEventListener('pagehide', handler);
    return () => {
      window.removeEventListener('pagehide', handler);
      // An in-app route change: the app keeps running, so an ordinary request completes and is
      // not held to keepalive's 64KB body cap. If it fails anyway the local mirror still has it.
      void flush();
    };
  }, [flush]);

  // A network blip: the failed value stays pending in `useAutosave`; resend it on reconnect.
  React.useEffect(() => {
    const onOnline = () => retry();
    window.addEventListener('online', onOnline);
    return () => window.removeEventListener('online', onOnline);
  }, [retry]);

  // Q4: an idle older tab must find out too, not only on its next keystroke. Checked on a timer
  // and whenever the tab comes back into view. Losing the draft first flushes what is pending, so
  // the server keeps it as History, then locks the form.
  const checkNow = React.useCallback(async () => {
    const claim = tokenRef.current;
    if (!claim || viewOnlyRef.current) return;
    try {
      const holder = await getQuotationDraftHolder(projectId, documentIdRef.current, claim);
      if (holder.is_holder) return;
      await flush();
      lockOut(holder.holder_name ?? null, holder.holder_at ?? null);
    } catch {
      // A failed check proves nothing; the next write or check will tell.
    }
  }, [projectId, flush, lockOut]);

  React.useEffect(() => {
    if (!ready || !token) return;
    let stopped = false;
    const check = () => {
      if (stopped || document.visibilityState === 'hidden') return;
      void checkNow();
    };
    const timer = window.setInterval(check, HOLDER_POLL_MS);
    const onVisible = () => {
      if (document.visibilityState === 'visible') check();
    };
    document.addEventListener('visibilitychange', onVisible);
    window.addEventListener('focus', onVisible);
    return () => {
      stopped = true;
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisible);
      window.removeEventListener('focus', onVisible);
    };
  }, [ready, token, checkNow]);

  const resume = React.useCallback(
    (value: QuotationFormState) => {
      writeMirror(mirrorKey(projectId, documentIdRef.current, tokenRef.current), {
        token: tokenRef.current,
        baseAt: serverAtRef.current,
        doc: value,
        at: new Date().toISOString(),
      });
      schedule(value);
    },
    [projectId, schedule],
  );

  const forgetLocalCopy = React.useCallback(() => {
    clearMirror(mirrorKey(projectId, documentIdRef.current, tokenRef.current));
  }, [projectId]);

  const setPaused = React.useCallback((paused: boolean) => {
    pausedRef.current = paused;
  }, []);

  return {
    status,
    savedAt,
    retry,
    flush,
    viewOnly,
    resume,
    setPaused,
    lockOut,
    checkNow,
    forgetLocalCopy,
  };
}
