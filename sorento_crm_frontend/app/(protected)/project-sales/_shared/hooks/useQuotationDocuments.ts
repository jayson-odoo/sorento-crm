'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import {
  ENTITY_DOWNLOADS_QUERY_KEY,
  MY_DOWNLOADS_QUERY_KEY,
} from '@/services/myDownloadsService';
import type { QuotationAmendmentDecision } from '../types/project.types';
import {
  addQuotationScope,
  applyQuotationAmendmentRequest,
  approveQuotationDocument,
  createQuotationDocument,
  createQuotationSignLink,
  decideQuotationAmendmentRow,
  deleteQuotationDocument,
  getQuotationAmendmentRequest,
  getQuotationApprovalGraph,
  getQuotationDocument,
  getQuotationLetterTemplates,
  issueQuotationDocument,
  listQuotationDocuments,
  listQuotationIssues,
  logQuotationWhatsAppOpened,
  moveQuotationApproval,
  queueQuotationIssuePdf,
  queueQuotationIssueXlsx,
  rejectQuotationDocument,
  reviseQuotationApproval,
  signQuotationDocument,
  updateQuotationDocument,
  updateQuotationScope,
  type QuotationDocument,
  type QuotationDocumentBody,
  type QuotationSignatureBody,
} from '../services/quotationDocumentService';

const DOCUMENTS_KEY = 'project-quotation-documents';
const ISSUES_KEY = 'project-quotation-issues';
const APPROVAL_GRAPH_KEY = ['quotation-approval-graph'];
/**
 * The customer's suggestions on a document. Invalidated by every write that can open or close a
 * version (issue, revise, approval moves, scope revise), because its `blocked_scopes` says
 * whether a hand-made draft now stands in the way of Apply.
 */
export const AMENDMENT_KEY = 'project-quotation-amendment';

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
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: [DOCUMENTS_KEY, projectId] });
    queryClient.invalidateQueries({ queryKey: [ISSUES_KEY, projectId] });
    queryClient.invalidateQueries({ queryKey: ['project-quotations'] });
    queryClient.invalidateQueries({ queryKey: ['project-quotation-versions'] });
    queryClient.invalidateQueries({ queryKey: [AMENDMENT_KEY] });
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
      toast.success(`Quotation ${document.document_no} created`);
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: QuotationDocumentBody }) =>
      updateQuotationDocument(projectId, id, body),
    onSuccess: () => {
      invalidate();
      toast.success('Quotation saved');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const remove = useMutation({
    mutationFn: (id: string) => deleteQuotationDocument(projectId, id),
    onSuccess: () => {
      invalidate();
      toast.success('Quotation deleted');
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
      toast.success('Quotation signed');
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
    documentId,
  };
}

export const quotationAmendmentKey = (projectId: string, documentId: string) => [
  AMENDMENT_KEY,
  projectId,
  documentId,
];

/** The customer's suggestions on this document's latest issue, or null (QUOTE-CUSTOMER-AMEND). */
export function useQuotationAmendmentRequest(
  projectId: string | undefined,
  documentId: string | undefined,
  enabled = true,
) {
  return useQuery({
    queryKey: quotationAmendmentKey(projectId ?? '', documentId ?? ''),
    queryFn: () => getQuotationAmendmentRequest(projectId as string, documentId as string),
    enabled: Boolean(projectId && documentId) && enabled,
  });
}

/**
 * Deciding a suggestion and applying the decisions. A decision only rewrites the request, so it
 * puts the answer straight into the cache; Apply opens draft versions, so it invalidates the
 * scopes and their versions as an issue does.
 */
export function useQuotationAmendmentMutations(projectId: string, documentId: string) {
  const queryClient = useQueryClient();
  const key = quotationAmendmentKey(projectId, documentId);

  const decide = useMutation({
    mutationFn: ({
      requestId,
      rowId,
      decision,
      reason,
    }: {
      requestId: string;
      rowId: string;
      decision: QuotationAmendmentDecision;
      reason?: string;
    }) =>
      decideQuotationAmendmentRow(projectId, documentId, requestId, rowId, { decision, reason }),
    onSuccess: (request) => queryClient.setQueryData(key, request),
    onError: (error: Error) => toast.error(error.message),
  });

  const apply = useMutation({
    mutationFn: (requestId: string) =>
      applyQuotationAmendmentRequest(projectId, documentId, requestId),
    onSuccess: (result) => {
      queryClient.setQueryData(key, result.request);
      queryClient.invalidateQueries({ queryKey: [DOCUMENTS_KEY, projectId] });
      queryClient.invalidateQueries({ queryKey: ['project-quotations'] });
      queryClient.invalidateQueries({ queryKey: ['project-quotation-versions'] });
      toast.success(
        result.version_ids.length > 0
          ? 'Decisions applied. The revision is a draft for you to check and send.'
          : 'Decisions applied. Nothing was accepted, so no revision was opened.',
      );
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return { decide, apply };
}
