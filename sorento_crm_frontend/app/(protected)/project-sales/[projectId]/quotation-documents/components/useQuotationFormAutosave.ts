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
 *   closed while offline still comes back on the next open (`readMirror`).
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
  doc: QuotationFormState;
  at: string;
};

export function mirrorKey(projectId: string, documentId: string | null): string {
  return documentId
    ? `quotation-form-draft:${documentId}`
    : `quotation-form-draft:new:${projectId}`;
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
};

export function useQuotationFormAutosave({
  projectId,
  documentId,
  token,
  state,
  isDirty,
  ready,
}: {
  projectId: string;
  /** The document, or null for a new proposal's private draft. */
  documentId: string | null;
  /** This tab's claim on the draft, from opening it; null until it has opened. */
  token: string | null;
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
  React.useEffect(() => {
    tokenRef.current = token;
    documentIdRef.current = documentId;
  }, [token, documentId]);

  const lockOut = React.useCallback((holderName: string | null, holderAt: string | null) => {
    viewOnlyRef.current = true;
    setViewOnly({ holderName, holderAt });
  }, []);

  const { status, savedAt, schedule, flush, retry } = useAutosave<QuotationFormState>(
    React.useCallback(
      async (value: QuotationFormState) => {
        if (pausedRef.current) return;
        const key = mirrorKey(projectId, documentIdRef.current);
        try {
          await saveQuotationFormDraft(
            projectId,
            documentIdRef.current,
            value,
            tokenRef.current ?? '',
            { keepalive: teardownRef.current },
          );
          clearMirror(key);
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
    writeMirror(mirrorKey(projectId, documentIdRef.current), {
      token: tokenRef.current,
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
  React.useEffect(() => {
    if (!ready || !token) return;
    let stopped = false;
    const check = async () => {
      if (stopped || viewOnlyRef.current || document.visibilityState === 'hidden') return;
      try {
        const holder = await getQuotationDraftHolder(projectId, documentIdRef.current, token);
        if (stopped || holder.is_holder) return;
        await flush();
        lockOut(holder.holder_name ?? null, holder.holder_at ?? null);
      } catch {
        // A failed check proves nothing; the next write or check will tell.
      }
    };
    const timer = window.setInterval(() => void check(), HOLDER_POLL_MS);
    const onVisible = () => {
      if (document.visibilityState === 'visible') void check();
    };
    document.addEventListener('visibilitychange', onVisible);
    window.addEventListener('focus', onVisible);
    return () => {
      stopped = true;
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisible);
      window.removeEventListener('focus', onVisible);
    };
  }, [ready, token, projectId, flush, lockOut]);

  const resume = React.useCallback(
    (value: QuotationFormState) => {
      writeMirror(mirrorKey(projectId, documentIdRef.current), {
        token: tokenRef.current,
        doc: value,
        at: new Date().toISOString(),
      });
      schedule(value);
    },
    [projectId, schedule],
  );

  const setPaused = React.useCallback((paused: boolean) => {
    pausedRef.current = paused;
  }, []);

  return { status, savedAt, retry, flush, viewOnly, resume, setPaused };
}
