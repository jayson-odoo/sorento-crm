'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  addQuotationScope,
  createQuotationDocument,
  createQuotationSignLink,
  deleteQuotationDocument,
  downloadQuotationIssuePdf,
  getQuotationDocument,
  issueQuotationDocument,
  listQuotationDocuments,
  listQuotationIssues,
  signQuotationDocument,
  updateQuotationDocument,
  updateQuotationScope,
  type QuotationDocument,
  type QuotationDocumentBody,
  type QuotationSignatureBody,
} from '../services/quotationDocumentService';

const DOCUMENTS_KEY = 'project-quotation-documents';
const ISSUES_KEY = 'project-quotation-issues';

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
      toast.success(`Issued as ${record.our_ref_text ?? `R${record.issue_no}`}`);
    },
    onError: (error: Error) => toast.error(error.message),
  });

  /**
   * Signing the draft. Deliberately does NOT run `invalidate()`.
   *
   * Nothing else on the document changed, and the document GET carries no signature, so a refetch
   * would answer with a record that looks unsigned and the screen would go back to asking for a
   * signature it had just been given. The caller keeps the returned signature (see
   * `QuotationDocumentClient`), which is also why it is not written into the query cache: react-
   * query refetches on window focus, and a cache entry would be silently overwritten the first
   * time the user tabbed away and back.
   */
  const sign = useMutation({
    mutationFn: ({ id, body }: { id: string; body: QuotationSignatureBody }) =>
      signQuotationDocument(projectId, id, body),
    onSuccess: () => toast.success('Quotation signed'),
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

  /** The issued PDF as bytes. The caller opens or saves it; a hook does not touch the DOM. */
  const issuePdf = useMutation({
    mutationFn: ({ id, issueId }: { id: string; issueId: string }) =>
      downloadQuotationIssuePdf(projectId, id, issueId),
    onError: (error: Error) => toast.error(error.message),
  });

  return {
    create,
    update,
    remove,
    addScope,
    renameScope,
    issue,
    sign,
    signLink,
    issuePdf,
    documentId,
  };
}
