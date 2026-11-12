'use client';

import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import { toast } from '@/lib/toast';
import { isOverridableRefusal } from '../lib/nonCancellable';
import {
  ENTITY_DOWNLOADS_QUERY_KEY,
  MY_DOWNLOADS_QUERY_KEY,
} from '@/services/myDownloadsService';
import type { QuotationFeedback } from '../types/project.types';
import {
  addQuotationScope,
  approveQuotationDocument,
  createQuotationDocument,
  openQuotationFormDraft,
  createQuotationSignLink,
  deleteQuotationDocument,
  duplicateQuotationDocument,
  getQuotationFeedback,
  getQuotationApprovalGraph,
  getQuotationDocument,
  getQuotationLetterTemplates,
  issueQuotationDocument,
  listQuotationDocuments,
  listQuotationIssues,
  listQuotationViews,
  logQuotationWhatsAppOpened,
  makeQuotation,
  moveQuotationApproval,
  previewQuotationCover,
  queueQuotationIssuePdf,
  queueQuotationIssueXlsx,
  rejectQuotationDocument,
  setQuotationFeedbackHandled,
  reviseQuotationApproval,
  signQuotationDocument,
  updateQuotationDocument,
  updateQuotationScope,
  documentNoun,
  type QuotationDocument,
  type QuotationCoverPreviewBody,
  type QuotationDocumentBody,
  type QuotationDuplicateBody,
  type QuotationSignatureBody,
} from '../services/quotationDocumentService';

const DOCUMENTS_KEY = 'project-quotation-documents';
const ISSUES_KEY = 'project-quotation-issues';
const VIEWS_KEY = 'project-quotation-views';
const APPROVAL_GRAPH_KEY = ['quotation-approval-graph'];
/**
 * The customer's feedback on a document (PS-QUOTE-MATRIX R19-R22). Read by the Customer feedback
 * tab, its badge and the Lines grid's marks; a column change refreshes it (cell labels).
 */
export const FEEDBACK_KEY = 'project-quotation-feedback';

export const quotationDocumentsKey = (projectId: string) => [DOCUMENTS_KEY, projectId];
export const quotationDocumentKey = (projectId: string, documentId: string) => [
  DOCUMENTS_KEY,
  projectId,
  documentId,
];

export function useQuotationDocuments(projectId: string | undefined) {
  return useQuery({
    queryKey: quotationDocumentsKey(projectId ?? ''),
    queryFn: () => listQuotationDocuments(projectId as string),
    enabled: Boolean(projectId),
  });
}

export function useQuotationDocument(
  projectId: string | undefined,
  documentId: string | undefined,
) {
  return useQuery({
    queryKey: quotationDocumentKey(projectId ?? '', documentId ?? ''),
    queryFn: () => getQuotationDocument(projectId as string, documentId as string),
    enabled: Boolean(projectId && documentId),
    // QUOTE-AUTOSAVE: the page's "Unsaved draft" line comes from the record, and the draft can be
    // written from another tab or person; coming back to the page re-reads it, even inside the
    // app-wide 30 s fresh window.
    refetchOnWindowFocus: 'always',
  });
}

/**
 * QUOTE-AUTOSAVE: open the form's draft, which claims it for this tab (owner, Q4): an existing
 * document's (`documentId`), or the person's own new-proposal draft (null). Run ONCE per visit (no
 * refetch on focus, mount or reconnect): a second open from the same tab would take the claim away
 * from itself, and the form seeds from the answer a single time. (Window focus never refetches:
 * the shared QueryProvider default.)
 */
export function useQuotationFormDraftOpen(projectId: string | undefined, documentId: string | null) {
  return useQuery({
    queryKey: ['project-quotation-form-draft-open', projectId ?? '', documentId ?? 'new'],
    queryFn: () => openQuotationFormDraft(projectId as string, documentId),
    enabled: Boolean(projectId),
    staleTime: Infinity,
    gcTime: 0,
    retry: false,
    refetchOnReconnect: false,
    refetchOnMount: false,
  });
}

/**
 * The cover page as it would print, from the form's unsaved values (nothing is stored). Settled
 * for 400 ms so typing does not request per keystroke; off until the tab that shows it is open.
 */
export function useQuotationCoverPreview(
  projectId: string | undefined,
  body: QuotationCoverPreviewBody,
  enabled = true,
) {
  const settled = useDebouncedValue(body, 400);
  return useQuery({
    queryKey: ['project-quotation-cover-preview', projectId ?? '', settled],
    queryFn: () => previewQuotationCover(projectId as string, settled),
    enabled: Boolean(projectId) && enabled,
    placeholderData: keepPreviousData,
    retry: false,
  });
}

/** The company's cover letter and terms for the create form (#1341). Read once per visit. */
export function useQuotationLetterTemplates(projectId: string | undefined, enabled = true) {
  return useQuery({
    queryKey: ['project-quotation-letter-templates', projectId ?? ''],
    queryFn: () => getQuotationLetterTemplates(projectId as string),
    enabled: Boolean(projectId) && enabled,
    staleTime: 60_000,
  });
}

export function useQuotationIssues(
  projectId: string | undefined,
  documentId: string | undefined,
) {
  return useQuery({
    queryKey: [ISSUES_KEY, projectId ?? '', documentId ?? ''],
    queryFn: () => listQuotationIssues(projectId as string, documentId as string),
    enabled: Boolean(projectId && documentId),
  });
}

/** The customer's counted opens of every revision's sign link (PS-QUOTE-VIEWS). */
export function useQuotationViews(projectId: string | undefined, documentId: string | undefined) {
  return useQuery({
    queryKey: [VIEWS_KEY, projectId ?? '', documentId ?? ''],
    queryFn: () => listQuotationViews(projectId as string, documentId as string),
    enabled: Boolean(projectId && documentId),
  });
}

/**
 * The `quotation` approval graph. One per install, so it is keyed on nothing and cached long:
 * an admin reshaping the graph is a Setup act, not something a quotation screen watches for.
 */
export function useQuotationApprovalGraph() {
  return useQuery({
    queryKey: APPROVAL_GRAPH_KEY,
    queryFn: getQuotationApprovalGraph,
    staleTime: 5 * 60 * 1000,
  });
}

export function useQuotationDocumentMutations(projectId: string, documentId?: string) {
  const queryClient = useQueryClient();

  /**
   * Issuing changes the scopes too - every version it named is frozen from that moment - so the
   * per-scope line queries are invalidated alongside the document. Refreshing only the document
   * would leave the line editor still offering edits the server now refuses.
   */
  /** The noun of the document this hook works on, read from the cache (it is on screen). */
  const cachedNoun = () =>
    documentNoun(
      documentId
        ? queryClient.getQueryData<QuotationDocument>(quotationDocumentKey(projectId, documentId))
        : undefined,
    );

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: [DOCUMENTS_KEY, projectId] });
    queryClient.invalidateQueries({ queryKey: [ISSUES_KEY, projectId] });
    queryClient.invalidateQueries({ queryKey: ['project-quotations'] });
    queryClient.invalidateQueries({ queryKey: ['project-quotation-versions'] });
    // A save may link the To party to the project and add its Attn people as stakeholders
    // (PROJECT-PARTY-ROLES PR 2): the project's parties, people and record are fresh again.
    queryClient.invalidateQueries({ queryKey: ['projects', 'parties', projectId] });
    queryClient.invalidateQueries({ queryKey: ['projects', 'stakeholders', projectId] });
    queryClient.invalidateQueries({ queryKey: ['projects', 'detail', projectId] });
  };

  /**
   * Both surfaces that show a queued export: the printer chip on this document
   * (`entity-downloads`) and the top-nav drawer. Refreshed together so the count moves on the
   * click rather than on the chip's next 4s poll.
   */
  const invalidateDownloads = () => {
    queryClient.invalidateQueries({ queryKey: ENTITY_DOWNLOADS_QUERY_KEY });
    queryClient.invalidateQueries({ queryKey: MY_DOWNLOADS_QUERY_KEY });
  };

  const create = useMutation({
    mutationFn: (body: QuotationDocumentBody = {}) => createQuotationDocument(projectId, body),
    onSuccess: (document: QuotationDocument) => {
      invalidate();
      toast.success(`Proposal ${document.document_no} created`);
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: QuotationDocumentBody }) =>
      updateQuotationDocument(projectId, id, body),
    onSuccess: (document: QuotationDocument) => {
      invalidate();
      toast.success(`${documentNoun(document)} saved`);
    },
    // An overridable non-cancellable refusal opens the form's override dialog instead.
    onError: (error: Error) => {
      if (!isOverridableRefusal(error)) toast.error(error.message);
    },
  });

  const remove = useMutation({
    mutationFn: (id: string) => deleteQuotationDocument(projectId, id),
    onSuccess: () => {
      invalidate();
      toast.success(`${cachedNoun()} deleted`);
    },
    // The server's 422 names withdrawal as the way out of an issued quotation, so it is shown
    // rather than replaced with a generic failure.
    onError: (error: Error) => toast.error(error.message),
  });

  const addScope = useMutation({
    mutationFn: ({ id, scopeLabel }: { id: string; scopeLabel: string }) =>
      addQuotationScope(projectId, id, { scope_label: scopeLabel }),
    onSuccess: (scope) => {
      invalidate();
      toast.success(`"${scope.scope_label}" added`);
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const renameScope = useMutation({
    mutationFn: ({
      id,
      scopeId,
      body,
    }: {
      id: string;
      scopeId: string;
      body: { scope_label?: string; sort_order?: number };
    }) => updateQuotationScope(projectId, id, scopeId, body),
    onSuccess: () => invalidate(),
    onError: (error: Error) => toast.error(error.message),
  });

  const issue = useMutation({
    mutationFn: (id: string) => issueQuotationDocument(projectId, id),
    onSuccess: (record) => {
      invalidate();
      toast.success(`Sent to the customer as ${record.our_ref_text ?? `R${record.issue_no}`}`);
    },
    onError: (error: Error) => toast.error(error.message),
  });

  /**
   * Signing the draft. The document GET now serializes `signatory_signature` / `is_signed`
   * (see `serialize_document`), so invalidating is what makes every reader of that query -
   * the Signatures tab included - pick up the new ink without a manual refresh. This used to
   * skip `invalidate()` and hand the caller the raw response to hold in local state instead;
   * that was working around a server gap that no longer exists, and the local copy was the
   * reason re-signing on the Scopes tab did not show up on the Signatures tab until reloaded.
   */
  const sign = useMutation({
    mutationFn: ({ id, body }: { id: string; body: QuotationSignatureBody }) =>
      signQuotationDocument(projectId, id, body),
    onSuccess: () => {
      invalidate();
      toast.success(`${cachedNoun()} signed`);
    },
    onError: (error: Error) => toast.error(error.message),
  });

  /**
   * The three approval acts. All three answer with the document, and all three invalidate the
   * same way an issue does: the Issue CTA, the block above it and the scope tabs all read the
   * document's approval position, so refreshing one of them alone leaves the screen disagreeing
   * with itself about whether it may be sent.
   */
  const submitForApproval = useMutation({
    mutationFn: ({ id, toStatusId }: { id: string; toStatusId: string }) =>
      moveQuotationApproval(projectId, id, toStatusId),
    onSuccess: (record: QuotationDocument) => {
      invalidate();
      toast.success(
        record.approval_status_key === 'pending_approval'
          ? 'Sent to a manager for approval'
          : record.approval_status_key === 'resubmitted'
            ? 'Appealed to a manager for approval'
            : `Moved to ${record.approval_status_label ?? 'draft'}`,
      );
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const approve = useMutation({
    mutationFn: (id: string) => approveQuotationDocument(projectId, id),
    onSuccess: () => {
      invalidate();
      toast.success('Quotation approved');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const reject = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      rejectQuotationDocument(projectId, id, reason),
    onSuccess: () => {
      invalidate();
      toast.success('Sent back to the salesperson');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const reviseApproval = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      reviseQuotationApproval(projectId, id, reason),
    onSuccess: () => {
      invalidate();
    },
    onError: (error: Error) => toast.error(error.message),
  });

  /**
   * Mint (or reuse) the tokenised counter-sign link for one issue. The server hands back a
   * RELATIVE path; the caller decides which origin to put in front of it.
   */
  const signLink = useMutation({
    mutationFn: ({ id, issueId }: { id: string; issueId: string }) =>
      createQuotationSignLink(projectId, id, issueId),
    onError: (error: Error) => toast.error(error.message),
  });

  /**
   * The activity line for a WhatsApp open. Fire and forget: opening WhatsApp is the real action
   * and the line is only a note, so a failure is never toasted.
   */
  const whatsAppOpened = useMutation({
    mutationFn: ({ id, issueId }: { id: string; issueId: string }) =>
      logQuotationWhatsAppOpened(projectId, id, issueId),
  });

  /**
   * Queue the issued PDF. The success toast is the whole feedback the click gets, because
   * nothing else happens in the browser: the file is generated by the worker and collected from
   * My Downloads or the printer chip on the document.
   *
   * Invalidating `entity-downloads` is what makes that chip's count move immediately - it is the
   * key `EntityDownloadsButton` reads, and without this the new row would not appear until its
   * next poll.
   */
  const issuePdf = useMutation({
    mutationFn: ({ id, issueId }: { id: string; issueId: string }) =>
      queueQuotationIssuePdf(projectId, id, issueId),
    onSuccess: () => {
      invalidateDownloads();
      toast.success('Preparing the PDF. It will appear in My Downloads.');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  /** PS-PROPOSAL-QUOTATION: a won project's proposal revision becomes its quotation. */
  const makeQuotationFrom = useMutation({
    mutationFn: ({ id, issueId }: { id: string; issueId: string }) =>
      makeQuotation(projectId, id, issueId),
    onSuccess: (document: QuotationDocument) => {
      invalidate();
      toast.success(`Quotation ${document.document_no} made`);
    },
    onError: (error: Error) => toast.error(error.message),
  });

  /** QUOTE-DUPLICATE-PARTY: the copy for another party. */
  const duplicate = useMutation({
    mutationFn: ({ id, body }: { id: string; body: QuotationDuplicateBody }) =>
      duplicateQuotationDocument(projectId, id, body),
    onSuccess: (document: QuotationDocument) => {
      invalidate();
      toast.success(`${document.document_no} made for ${document.recipient_name_snapshot ?? 'the party'}`);
    },
    onError: (error: Error) => toast.error(error.message),
  });

  /** The issued workbook, queued the same way and reported the same way. */
  const issueXlsx = useMutation({
    mutationFn: ({ id, issueId }: { id: string; issueId: string }) =>
      queueQuotationIssueXlsx(projectId, id, issueId),
    onSuccess: () => {
      invalidateDownloads();
      toast.success('Preparing the Excel file. It will appear in My Downloads.');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return {
    create,
    update,
    remove,
    addScope,
    renameScope,
    issue,
    whatsAppOpened,
    submitForApproval,
    approve,
    reject,
    reviseApproval,
    sign,
    signLink,
    issuePdf,
    issueXlsx,
    makeQuotationFrom,
    duplicate,
    documentId,
  };
}

export const quotationFeedbackKey = (projectId: string, documentId: string) => [
  FEEDBACK_KEY,
  projectId,
  documentId,
];

/** Every feedback note on this document, and how many are still open. */
export function useQuotationFeedback(
  projectId: string | undefined,
  documentId: string | undefined,
  enabled = true,
) {
  return useQuery({
    queryKey: quotationFeedbackKey(projectId ?? '', documentId ?? ''),
    queryFn: () => getQuotationFeedback(projectId as string, documentId as string),
    enabled: Boolean(projectId && documentId) && enabled,
  });
}

/**
 * Handled, the one action a note has. The tick lands in the cache at once (the badge and the
 * grid's marks move with it) and the read is refreshed for who and when.
 */
export function useQuotationFeedbackMutation(projectId: string, documentId: string) {
  const queryClient = useQueryClient();
  const key = quotationFeedbackKey(projectId, documentId);

  return useMutation({
    mutationFn: ({ rowId, handled }: { rowId: string; handled: boolean }) =>
      setQuotationFeedbackHandled(projectId, documentId, rowId, handled),
    onMutate: async ({ rowId, handled }) => {
      await queryClient.cancelQueries({ queryKey: key });
      const previous = queryClient.getQueryData<QuotationFeedback>(key);
      if (previous) {
        let open = previous.open_count;
        const requests = previous.requests.map((request) => ({
          ...request,
          rows: request.rows.map((row) => {
            if (row.id !== rowId || Boolean(row.handled_at) === handled) return row;
            open += handled ? -1 : 1;
            return { ...row, handled_at: handled ? new Date().toISOString() : null };
          }),
        }));
        queryClient.setQueryData<QuotationFeedback>(key, { open_count: open, requests });
      }
      return { previous };
    },
    onError: (error: Error, _variables, context) => {
      if (context?.previous) queryClient.setQueryData(key, context.previous);
      toast.error(error.message);
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: key }),
  });
}
