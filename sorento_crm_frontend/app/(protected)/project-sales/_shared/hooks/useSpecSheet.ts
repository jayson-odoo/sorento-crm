'use client';

import { keepPreviousData, useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
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
  getSpecSheetPageImages,
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
 * No query refetches on window focus: the app's QueryProvider turns that off for every query. The
 * reader holds a page stack and a window of previews; a tab switch that refetched them all is the
 * bottleneck the owner asked not to repeat. Data changes only through the mutations below, which
 * invalidate exactly what they touch.
 */
/** A fetched preview chunk is good until a write invalidates it. */
const PREVIEW_STALE_MS = 5 * 60_000;
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
  });
}

export function useSpecSheetDetail(projectId: string, documentId: string, sheetId: string) {
  return useQuery({
    queryKey: specSheetDetailKey(documentId, sheetId),
    queryFn: () => getSpecSheet(projectId, documentId, sheetId),
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
    queryKey: [...specSheetPreviewPrefix(documentId, sheetId), sorted],
    queryFn: () => getSpecSheetPreview(projectId, documentId, sheetId, sorted),
    enabled: enabled && sorted.length > 0,
    retry: false,
    // Scrolling to a new window keeps the pages both windows share on screen while the next
    // preview loads, instead of blanking them.
    placeholderData: keepPreviousData,
    staleTime: PREVIEW_STALE_MS,
  });
}

/**
 * One preview query per chunk of pages. A chunk's key is its own sorted keys, so scrolling back to
 * a chunk already fetched is a cache hit and a fast scroll costs one call per chunk, not per page.
 */
export function useSpecSheetPreviews(
  projectId: string,
  documentId: string,
  sheetId: string,
  chunks: string[][],
) {
  return useQueries({
    queries: chunks.map((keys) => {
      const sorted = [...keys].sort();
      return {
        queryKey: [...specSheetPreviewPrefix(documentId, sheetId), sorted],
        queryFn: () => getSpecSheetPreview(projectId, documentId, sheetId, sorted),
        enabled: sorted.length > 0,
        retry: false,
        // Scrolling back to a chunk is a cache hit; writes invalidate the previews explicitly.
        staleTime: PREVIEW_STALE_MS,
      };
    }),
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
    // The designer owns its layers once opened; a background refetch would not reach them.
    staleTime: Infinity,
  });
}

/**
 * The ONE open page's pictures at medium size. `key` is null until the reader has settled on a
 * page, so a fast scroll asks for nothing. Cached like the previews; nothing here refetches by
 * itself.
 */
export function useSpecSheetPageImages(
  projectId: string,
  documentId: string,
  sheetId: string,
  key: string | null,
) {
  return useQuery({
    queryKey: [...specSheetPreviewPrefix(documentId, sheetId), 'page-images', key],
    queryFn: () => getSpecSheetPageImages(projectId, documentId, sheetId, key as string),
    enabled: key !== null,
    retry: false,
    staleTime: PREVIEW_STALE_MS,
  });
}

export function useSpecSheetMutations(projectId: string, documentId: string) {
  const queryClient = useQueryClient();

  const refreshSheet = (sheetId: string, detail?: SpecSheetDetail) => {
    // The answer of a write IS the sheet's new detail: keep it, no second read. Without one the
    // detail is read again.
    if (detail) queryClient.setQueryData(specSheetDetailKey(documentId, sheetId), detail);
    else queryClient.invalidateQueries({ queryKey: specSheetDetailKey(documentId, sheetId) });
    queryClient.invalidateQueries({ queryKey: specSheetListKey(documentId) });
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
