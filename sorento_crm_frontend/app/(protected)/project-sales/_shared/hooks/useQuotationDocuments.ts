'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  addQuotationScope,
  createQuotationDocument,
  deleteQuotationDocument,
  getQuotationDocument,
  issueQuotationDocument,
  listQuotationDocuments,
  listQuotationIssues,
  updateQuotationDocument,
  updateQuotationScope,
  type QuotationDocument,
  type QuotationDocumentBody,
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

  return { create, update, remove, addScope, renameScope, issue, documentId };
}
