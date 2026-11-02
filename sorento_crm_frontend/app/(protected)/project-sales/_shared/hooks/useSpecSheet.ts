'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import {
  ENTITY_DOWNLOADS_QUERY_KEY,
  MY_DOWNLOADS_QUERY_KEY,
} from '@/services/myDownloadsService';
import {
  getSpecSheet,
  getSpecSheetPreview,
  queueSpecSheetPdf,
  saveSpecSheet,
  type SpecSheetSettingsBody,
  type SpecSheetView,
} from '../services/specSheetService';

/** PS-SPEC-SHEET: the Spec sheet tab's reads and writes. */
const SPEC_SHEET_KEY = 'project-quotation-spec-sheet';
const SPEC_SHEET_PREVIEW_KEY = 'project-quotation-spec-sheet-preview';

export const specSheetKey = (documentId: string, issueId: string | null) => [
  SPEC_SHEET_KEY,
  documentId,
  issueId ?? 'latest',
];

export function useSpecSheet(projectId: string, documentId: string, issueId: string | null) {
  return useQuery({
    queryKey: specSheetKey(documentId, issueId),
    queryFn: () => getSpecSheet(projectId, documentId, issueId),
  });
}

/** The pages as they will print. Only asked for once the templates are chosen. */
export function useSpecSheetPreview(
  projectId: string,
  documentId: string,
  issueId: string | null,
  enabled: boolean,
) {
  return useQuery({
    queryKey: [SPEC_SHEET_PREVIEW_KEY, documentId, issueId ?? 'latest'],
    queryFn: () => getSpecSheetPreview(projectId, documentId, issueId),
    enabled,
    retry: false,
  });
}

export function useSpecSheetMutations(projectId: string, documentId: string) {
  const queryClient = useQueryClient();

  const save = useMutation({
    mutationFn: (body: SpecSheetSettingsBody) => saveSpecSheet(projectId, documentId, body),
    onSuccess: (view: SpecSheetView) => {
      // Every revision's view reads the same settings, so all of them go stale.
      queryClient.invalidateQueries({ queryKey: [SPEC_SHEET_KEY, documentId] });
      queryClient.invalidateQueries({ queryKey: [SPEC_SHEET_PREVIEW_KEY, documentId] });
      queryClient.setQueryData(specSheetKey(documentId, view.issue_id), view);
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const exportPdf = useMutation({
    mutationFn: (issueId: string | null) => queueSpecSheetPdf(projectId, documentId, issueId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ENTITY_DOWNLOADS_QUERY_KEY });
      queryClient.invalidateQueries({ queryKey: MY_DOWNLOADS_QUERY_KEY });
      toast.success('Preparing the spec sheet. It will appear in My Downloads.');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return { save, exportPdf };
}
