/**
 * SAMPLE-FROM-QUOTE: a NEW sample request starts with its project's quotation lines (UAC
 * SFQ-20..24). Used by both forms that create sample requests (the shared portal form, which is
 * also the CRM's My Requests form, and the staff form; owner Q6 a), each passing its own fetcher.
 *
 * The rows are replaced only while they are still untouched pre-fill (or blank): a person's
 * deletes, additions and edits always win, and then the source quotation is dropped instead.
 */
import { useEffect, useRef, useState } from 'react';

import {
  linesUntouched,
  prefillFromQuotation,
  prefillNote,
  type FormState,
} from '@/lib/sample-request-form';
import type {
  SampleRequestQuotationOption,
  SampleRequestQuotationPrefill,
} from '@/types/sampleRequest';

const NO_SOURCE: Partial<FormState> = {
  quotation_document_id: '',
  quotation_issue_id: '',
  prefill_signature: '',
};

export function useSampleRequestPrefill({
  enabled,
  projectId,
  state,
  patch,
  fetchPrefill,
}: {
  /** False when editing an existing request: a draft is never re-filled (SFQ-21). */
  enabled: boolean;
  projectId: string;
  state: FormState;
  patch: (next: Partial<FormState>) => void;
  fetchPrefill: (
    projectId: string,
    documentId?: string,
  ) => Promise<SampleRequestQuotationPrefill>;
}) {
  const [documents, setDocuments] = useState<SampleRequestQuotationOption[]>([]);
  const [documentId, setDocumentId] = useState<string | undefined>(undefined);
  const [note, setNote] = useState<string | null>(null);
  // The document the last read answered with: the server's default until one is picked.
  const [answered, setAnswered] = useState<string | null>(null);

  // Read at response time, not at request time: the person may edit rows while the read is out.
  const latest = useRef(state);
  latest.current = state;
  const fetcher = useRef(fetchPrefill);
  fetcher.current = fetchPrefill;
  const patchRef = useRef(patch);
  patchRef.current = patch;

  // A recorded quotation belongs to the project it was recorded on. When the project moves away
  // (a new request or a loaded draft alike), the source goes, so the save is never refused for a
  // stranger's quotation; the rows stay, and untouched pre-fill can still be replaced.
  const sourceProject = useRef<string | null>(null);
  useEffect(() => {
    if (!state.quotation_document_id) {
      sourceProject.current = null;
    } else if (sourceProject.current === null) {
      sourceProject.current = projectId;
    } else if (sourceProject.current !== projectId) {
      sourceProject.current = null;
      patchRef.current({ quotation_document_id: '', quotation_issue_id: '' });
    }
  }, [projectId, state.quotation_document_id]);

  // A new project starts from its default quotation.
  const [forProject, setForProject] = useState(projectId);
  if (forProject !== projectId) {
    setForProject(projectId);
    setDocumentId(undefined);
  }

  useEffect(() => {
    if (!enabled) return;
    if (!projectId) {
      setDocuments([]);
      setNote(null);
      setAnswered(null);
      if (latest.current.quotation_document_id || latest.current.prefill_signature) {
        patchRef.current(NO_SOURCE);
      }
      return;
    }
    let cancelled = false;
    // Through a resolved promise, so a fetcher that throws outright still lands in .catch.
    Promise.resolve()
      .then(() => fetcher.current(projectId, documentId))
      .then((answer) => {
        if (cancelled) return;
        // A malformed answer pre-fills nothing rather than breaking the form.
        const prefill: SampleRequestQuotationPrefill = {
          documents: answer?.documents ?? [],
          document_id: answer?.document_id ?? null,
          issue_id: answer?.issue_id ?? null,
          lines: answer?.lines ?? [],
          skipped: answer?.skipped ?? [],
        };
        setDocuments(prefill.documents);
        setAnswered(prefill.document_id);
        if (linesUntouched(latest.current)) {
          patchRef.current(prefillFromQuotation(prefill));
          setNote(prefillNote(prefill));
        } else {
          patchRef.current(NO_SOURCE);
          setNote(null);
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [enabled, projectId, documentId]);

  return {
    /** The project's quotation documents, while the rows are still the pre-fill's own: once the
     * person edits them a pick would change nothing, so no picker is offered. */
    documents: linesUntouched(state) ? documents : [],
    /** The picked document, else the one the server defaulted to. */
    documentId: documentId ?? answered ?? undefined,
    pickDocument: setDocumentId,
    /** One line naming the quotation lines that did not become rows, or null. */
    note,
  };
}
