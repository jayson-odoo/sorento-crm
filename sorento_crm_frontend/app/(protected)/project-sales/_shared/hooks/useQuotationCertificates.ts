'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import {
  ENTITY_DOWNLOADS_QUERY_KEY,
  MY_DOWNLOADS_QUERY_KEY,
} from '@/services/myDownloadsService';
import {
  addQuotationCertificate,
  getQuotationCertificate,
  listQuotationCertificates,
  queueQuotationCertificatesPdf,
  resetQuotationCertificateBoxes,
  saveQuotationCertificateBoxes,
  setQuotationCertificateSend,
  type BoxScope,
  type CertificateBox,
} from '../services/quotationCertificateService';

/** The Certification tab: its list, one certificate page and their writes. */
const LIST_KEY = 'quotation-certificates';
const DETAIL_KEY = 'quotation-certificate';

export const quotationCertificatesKey = (documentId: string) => [LIST_KEY, documentId];
export const quotationCertificateKey = (documentId: string, certificateId: string) => [
  DETAIL_KEY,
  documentId,
  certificateId,
];

export function useQuotationCertificates(projectId: string, documentId: string) {
  return useQuery({
    queryKey: quotationCertificatesKey(documentId),
    queryFn: () => listQuotationCertificates(projectId, documentId),
  });
}

export function useQuotationCertificate(
  projectId: string,
  documentId: string,
  certificateId: string,
) {
  return useQuery({
    queryKey: quotationCertificateKey(documentId, certificateId),
    queryFn: () => getQuotationCertificate(projectId, documentId, certificateId),
  });
}

export function useQuotationCertificateMutations(projectId: string, documentId: string) {
  const queryClient = useQueryClient();
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: quotationCertificatesKey(documentId) });
    queryClient.invalidateQueries({ queryKey: [DETAIL_KEY, documentId] });
  };
  const onError = (error: Error) => toast.error(error.message);

  const add = useMutation({
    mutationFn: (certificateId: string) =>
      addQuotationCertificate(projectId, documentId, certificateId),
    onSuccess: () => {
      refresh();
      toast.success('Certificate added');
    },
    onError,
  });

  const saveBoxes = useMutation({
    mutationFn: (v: { certificateId: string; scope: BoxScope; boxes: CertificateBox[] }) =>
      saveQuotationCertificateBoxes(projectId, documentId, v.certificateId, v.scope, v.boxes),
    onSuccess: () => {
      refresh();
      toast.success('Boxes saved');
    },
    onError,
  });

  const resetBoxes = useMutation({
    mutationFn: (certificateId: string) =>
      resetQuotationCertificateBoxes(projectId, documentId, certificateId),
    onSuccess: () => {
      refresh();
      toast.success('Boxes reset');
    },
    onError,
  });

  const setSend = useMutation({
    mutationFn: (v: { certificateId: string; value: boolean | null }) =>
      setQuotationCertificateSend(projectId, documentId, v.certificateId, v.value),
    onSuccess: refresh,
    onError,
  });

  const exportPdf = useMutation({
    mutationFn: (issueId: string | null) =>
      queueQuotationCertificatesPdf(projectId, documentId, issueId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ENTITY_DOWNLOADS_QUERY_KEY });
      queryClient.invalidateQueries({ queryKey: MY_DOWNLOADS_QUERY_KEY });
      toast.success('Preparing the certificates. They will appear in My Downloads.');
    },
    onError,
  });

  return { add, saveBoxes, resetBoxes, setSend, exportPdf };
}
