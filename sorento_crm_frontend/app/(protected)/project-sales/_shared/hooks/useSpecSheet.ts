'use client';

import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import type { TagLayer } from '@/lib/dealer-kit/tag-template-types';
import {
  ENTITY_DOWNLOADS_QUERY_KEY,
  MY_DOWNLOADS_QUERY_KEY,
} from '@/services/myDownloadsService';
import {
  createSpecSheet,
  getSpecSheet,
  getSpecSheetPageDesign,
  getSpecSheetPreview,
  listSpecSheets,
  queueSpecSheetPdf,
  saveSpecSheetPageEdit,
  updateSpecSheet,
  type CreateSpecSheetBody,
  type SpecSheetDetail,
  type UpdateSpecSheetBody,
} from '../services/specSheetService';

/**
 * SPEC-SHEET-V2: the spec sheet list, the reader and the page designer.
 *
 * Every query opts out of refetch on window focus. The reader holds a page stack and a window of
 * previews; a tab switch that refetched them all is the bottleneck the owner asked not to
 * repeat. Data changes only through the mutations below, which invalidate exactly what they touch.
 */
const LIST_KEY = 'project-spec-sheets';
const DETAIL_KEY = 'project-spec-sheet';
const PREVIEW_KEY = 'project-spec-sheet-preview';
const DESIGN_KEY = 'project-spec-sheet-design';

export const specSheetListKey = (documentId: string) => [LIST_KEY, documentId];
export const specSheetDetailKey = (documentId: string, sheetId: string) => [
  DETAIL_KEY,
  documentId,
  sheetId,
];
/** Every preview window of one sheet, for invalidation. */
export const specSheetPreviewPrefix = (documentId: string, sheetId: string) => [
  PREVIEW_KEY,
  documentId,
  sheetId,
];

export function useSpecSheets(projectId: string, documentId: string) {
  return useQuery({
    queryKey: specSheetListKey(documentId),
    queryFn: () => listSpecSheets(projectId, documentId),
    refetchOnWindowFocus: false,
  });
}

export function useSpecSheetDetail(projectId: string, documentId: string, sheetId: string) {
  return useQuery({
    queryKey: specSheetDetailKey(documentId, sheetId),
    queryFn: () => getSpecSheet(projectId, documentId, sheetId),
    refetchOnWindowFocus: false,
  });
}

/**
 * One window of pages. The key is the SORTED keys, so the same window in another order is one
 * request.
 */
export function useSpecSheetPreview(
  projectId: string,
  documentId: string,
  sheetId: string,
  keys: string[],
  enabled = true,
) {
  const sorted = [...keys].sort();
  return useQuery({
    queryKey: [...specSheetPreviewPrefix(documentId, sheetId), sorted.join(',')],
    queryFn: () => getSpecSheetPreview(projectId, documentId, sheetId, sorted),
    enabled: enabled && sorted.length > 0,
    refetchOnWindowFocus: false,
    retry: false,
    // Scrolling to a new window keeps the pages both windows share on screen while the next
    // preview loads, instead of blanking them.
    placeholderData: keepPreviousData,
  });
}

export function useSpecSheetPageDesign(
  projectId: string,
  documentId: string,
  sheetId: string,
  key: string,
) {
  return useQuery({
    queryKey: [DESIGN_KEY, documentId, sheetId, key],
    queryFn: () => getSpecSheetPageDesign(projectId, documentId, sheetId, key),
    refetchOnWindowFocus: false,
    // The designer owns its layers once opened; a background refetch would not reach them.
    staleTime: Infinity,
  });
}

export function useSpecSheetMutations(projectId: string, documentId: string) {
  const queryClient = useQueryClient();

  const refreshSheet = (sheetId: string, detail?: SpecSheetDetail) => {
    // The answer of a write IS the sheet's new detail: show it now, then confirm with a read.
    if (detail) queryClient.setQueryData(specSheetDetailKey(documentId, sheetId), detail);
    queryClient.invalidateQueries({ queryKey: specSheetListKey(documentId) });
    queryClient.invalidateQueries({ queryKey: specSheetDetailKey(documentId, sheetId) });
    queryClient.invalidateQueries({ queryKey: specSheetPreviewPrefix(documentId, sheetId) });
    queryClient.invalidateQueries({ queryKey: [DESIGN_KEY, documentId, sheetId] });
  };

  const create = useMutation({
    mutationFn: (body: CreateSpecSheetBody) => createSpecSheet(projectId, documentId, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: specSheetListKey(documentId) });
    },
  });

  const update = useMutation({
    mutationFn: ({ sheetId, body }: { sheetId: string; body: UpdateSpecSheetBody }) =>
      updateSpecSheet(projectId, documentId, sheetId, body),
    onSuccess: (detail, { sheetId }) => refreshSheet(sheetId, detail),
    onError: (error: Error) => toast.error(error.message),
  });

  const savePageEdit = useMutation({
    mutationFn: ({ sheetId, key, layers }: { sheetId: string; key: string; layers: TagLayer[] }) =>
      saveSpecSheetPageEdit(projectId, documentId, sheetId, key, layers),
    onSuccess: (detail, { sheetId }) => refreshSheet(sheetId, detail),
    onError: (error: Error) => toast.error(error.message),
  });

  const exportPdf = useMutation({
    mutationFn: (sheetId: string) => queueSpecSheetPdf(projectId, documentId, sheetId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ENTITY_DOWNLOADS_QUERY_KEY });
      queryClient.invalidateQueries({ queryKey: MY_DOWNLOADS_QUERY_KEY });
      queryClient.invalidateQueries({ queryKey: specSheetListKey(documentId) });
      toast.success('Preparing the spec sheet. It will appear in My Downloads.');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return { create, update, savePageEdit, exportPdf };
}
