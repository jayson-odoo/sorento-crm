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

  // Read at response time, not at request time: the person may edit rows while the read is out.
  const latest = useRef(state);
  latest.current = state;
  const fetcher = useRef(fetchPrefill);
  fetcher.current = fetchPrefill;
  const patchRef = useRef(patch);
  patchRef.current = patch;

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
      if (latest.current.quotation_document_id || latest.current.prefill_signature) {
        patchRef.current(NO_SOURCE);
      }
      return;
    }
    let cancelled = false;
    fetcher
      .current(projectId, documentId)
      .then((prefill) => {
        if (cancelled) return;
        setDocuments(prefill.documents);
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
    /** The project's quotation documents; the form shows a picker only for more than one. */
    documents,
    /** The picked document, or undefined for the server's default. */
    documentId,
    pickDocument: setDocumentId,
    /** One line naming the quotation lines that did not become rows, or null. */
    note,
  };
}
