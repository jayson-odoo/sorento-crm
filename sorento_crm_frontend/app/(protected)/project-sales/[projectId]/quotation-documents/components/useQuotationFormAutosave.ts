'use client';

import * as React from 'react';
import { useAutosave, type AutosaveStatus } from '@/hooks/useAutosave';
import {
  saveQuotationFormDraft,
  StaleDraftError,
  type QuotationDocument,
  type QuotationFormState,
} from '../../../_shared/services/quotationDocumentService';

/**
 * QUOTE-AUTOSAVE: the proposal / quotation form's autosave (plan
 * `documentation/plans/project-sales/PLAN-quote-autosave-10nov.md`, card rules 1-2).
 *
 * The tag designer's own debounce (`hooks/useAutosave`, 1 s after the last change, saves
 * serialised, `flush`, `retry`) writing the document's DRAFT, never the record:
 *
 * - **First real edit of a new proposal** creates it (`create`), with the draft in the same
 *   request, so the number and the typing land together. Every later save is `PUT .../form-draft`.
 * - **Every edit** is mirrored to this browser's local storage until the server has it, so a tab
 *   closed while offline still comes back on the next open (`readMirror`).
 * - **Leaving** flushes: an in-app route change unmounts the form (cleanup below), a refresh or a
 *   closed tab fires `pagehide` (sent `keepalive`, so it outlives the page). The same two exits
 *   the request designer covers (`RequestTagDesigner.tsx:1110-1136`).
 * - **Back online** retries the failed save on its own.
 * - **Two tabs** (card Q4): each save names the draft revision it was built on; a stale one comes
 *   back 409, the server keeps its state as a History entry, and this hook stops saving and
 *   reports `conflict` until the page is reloaded.
 */

export type MirroredDraft = {
  baseRev: number;
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

export type DraftConflict = { updatedByName: string | null; updatedAt: string | null };

export type UseQuotationFormAutosave = {
  status: AutosaveStatus;
  savedAt: Date | null;
  retry: () => void;
  flush: () => Promise<void>;
  /** The document's id: the route's, or the one the first edit created. */
  documentId: string | null;
  /** The draft revision this tab last wrote or read. */
  rev: React.MutableRefObject<number>;
  conflict: DraftConflict | null;
  /** A draft exists on the server for this document (Discard draft, the read page strip). */
  hasDraft: boolean;
  setHasDraft: (value: boolean) => void;
  /** Save `state` as soon as the debounce allows: an unsent local copy the form reopened on. */
  resume: (state: QuotationFormState) => void;
};

export function useQuotationFormAutosave({
  projectId,
  initialDocumentId,
  initialRev,
  initialHasDraft,
  state,
  isDirty,
  ready,
  create,
  onCreated,
}: {
  projectId: string;
  initialDocumentId: string | null;
  /** The draft revision the form opened on; null until it is known. */
  initialRev: number | null;
  initialHasDraft: boolean;
  /** The form's state, or null until the form has its starting point. */
  state: QuotationFormState | null;
  /** Something has been typed: before that, a changing state is the form loading, not an edit. */
  isDirty: boolean;
  /** The form has loaded and may save (false while locked or still loading). */
  ready: boolean;
  /** A new proposal's first save: create the record with this state as its draft. */
  create: (state: QuotationFormState) => Promise<QuotationDocument>;
  onCreated: (document: QuotationDocument) => void;
}): UseQuotationFormAutosave {
  const [documentId, setDocumentId] = React.useState<string | null>(initialDocumentId);
  const documentIdRef = React.useRef<string | null>(initialDocumentId);
  const rev = React.useRef<number>(initialRev ?? 0);
  const [conflict, setConflict] = React.useState<DraftConflict | null>(null);
  const conflictRef = React.useRef(false);
  const [hasDraft, setHasDraft] = React.useState(initialHasDraft);
  const teardownRef = React.useRef(false);

  React.useEffect(() => {
    if (initialRev !== null) rev.current = initialRev;
  }, [initialRev]);
  React.useEffect(() => {
    setHasDraft(initialHasDraft);
  }, [initialHasDraft]);

  const createRef = React.useRef(create);
  const onCreatedRef = React.useRef(onCreated);
  React.useEffect(() => {
    createRef.current = create;
    onCreatedRef.current = onCreated;
  }, [create, onCreated]);

  const { status, savedAt, schedule, flush, retry } = useAutosave<QuotationFormState>(
    React.useCallback(
      async (value: QuotationFormState) => {
        if (conflictRef.current) return;
        const currentId = documentIdRef.current;
        const key = mirrorKey(projectId, currentId);
        try {
          if (!currentId) {
            const created = await createRef.current(value);
            documentIdRef.current = created.id;
            rev.current = 1;
            setDocumentId(created.id);
            clearMirror(key);
            onCreatedRef.current(created);
          } else {
            const result = await saveQuotationFormDraft(projectId, currentId, value, rev.current, {
              keepalive: teardownRef.current,
            });
            rev.current = result.rev;
            clearMirror(key);
          }
          setHasDraft(true);
        } catch (error) {
          if (error instanceof StaleDraftError) {
            // The server kept this tab's state as a History entry; the local copy is not needed.
            conflictRef.current = true;
            clearMirror(key);
            setConflict({ updatedByName: error.updatedByName, updatedAt: error.updatedAt });
          }
          throw error;
        }
      },
      [projectId],
    ),
  );

  // Every REAL edit schedules a save (card rule 1). Guarded on the serialised VALUE, not a "have I
  // run" flag: the first value is the form's starting point and only moves the baseline, and so
  // does any change made before anything was typed (a template default, a scope opened and seeded
  // from the server). Comparing values also makes StrictMode's double effect pass a no-op.
  const lastSeen = React.useRef<string | undefined>(undefined);
  React.useEffect(() => {
    if (!ready || state === null) return;
    // The live total is left out of the comparison: opening a saved scope swaps the server's figure
    // for the staged lines' own sum, the same money written differently, and that is not an edit.
    const json = JSON.stringify({ ...state, total: undefined });
    if (json === lastSeen.current) return;
    const isInitial = lastSeen.current === undefined;
    lastSeen.current = json;
    if (isInitial || !isDirty || conflictRef.current) return;
    writeMirror(mirrorKey(projectId, documentIdRef.current), {
      baseRev: rev.current,
      doc: state,
      at: new Date().toISOString(),
    });
    schedule(state);
  }, [state, isDirty, ready, schedule, projectId]);

  // Leaving the page, both ways it can happen (card rule 2).
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

  const resume = React.useCallback(
    (value: QuotationFormState) => {
      writeMirror(mirrorKey(projectId, documentIdRef.current), {
        baseRev: rev.current,
        doc: value,
        at: new Date().toISOString(),
      });
      schedule(value);
    },
    [projectId, schedule],
  );

  return {
    status,
    savedAt,
    retry,
    flush,
    documentId,
    rev,
    conflict,
    hasDraft,
    setHasDraft,
    resume,
  };
}
