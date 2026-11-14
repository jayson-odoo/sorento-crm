'use client';

import {
  keepPreviousData,
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query';
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
  applySpecSheetLayerToAll,
  listSpecSheets,
  addSpecSheetLayerToAll,
  queueSpecSheetPdf,
  saveSpecSheetPageEdit,
  updateSpecSheet,
  type ApplyAllChanges,
  type CreateSpecSheetBody,
  type SpecSheetPreview,
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

export function useSpecSheetDetail(
  projectId: string,
  documentId: string,
  sheetId: string,
) {
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
 * Which template versions a sheet prints from (cover, page, single item), as the previews' cache
 * key part. Templates and Use latest templates change it.
 */
export function templateSignature(detail: Pick<SpecSheetDetail, 'templates'>): string {
  return (['cover', 'page', 'single'] as const)
    .map((part) => {
      const t = detail.templates?.[part];
      return t ? `${t.id}@${t.version_no}` : '-';
    })
    .join('|');
}

/**
 * One preview query per chunk of pages. A chunk's key is its own sorted keys, so scrolling back to
 * a chunk already fetched is a cache hit and a fast scroll costs one call per chunk, not per page.
 *
 * `templates` names the template versions the sheet prints from. It is part of the key so a
 * template switch can never draw a chunk cached from the old templates, not even for the moment
 * a stale cache entry shows before its refetch: a live page seeds its canvas from the first
 * payload it gets and would keep the old layers.
 */
export function useSpecSheetPreviews(
  projectId: string,
  documentId: string,
  sheetId: string,
  chunks: string[][],
  templates = '',
) {
  return useQueries({
    queries: chunks.map((keys) => {
      const sorted = [...keys].sort();
      return {
        queryKey: [
          ...specSheetPreviewPrefix(documentId, sheetId),
          sorted,
          templates,
        ],
        queryFn: () =>
          getSpecSheetPreview(projectId, documentId, sheetId, sorted),
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
    queryKey: [
      ...specSheetPreviewPrefix(documentId, sheetId),
      'page-images',
      key,
    ],
    queryFn: () =>
      getSpecSheetPageImages(projectId, documentId, sheetId, key as string),
    enabled: key !== null,
    retry: false,
    staleTime: PREVIEW_STALE_MS,
  });
}

export function useSpecSheetMutations(projectId: string, documentId: string) {
  const queryClient = useQueryClient();

  const refreshSheet = (sheetId: string, detail?: SpecSheetDetail) => {
    // The previews are cached per template versions (`useSpecSheetPreviews`). When a write moved
    // the sheet to other templates, the chunks on screen are still keyed by the OLD versions until
    // the next render: refetching them now would file the new template's pages under the old
    // key, and switching back would draw them. Mark them stale only; the new keys fetch themselves.
    const before = queryClient.getQueryData<SpecSheetDetail>(
      specSheetDetailKey(documentId, sheetId),
    );
    const switched =
      detail !== undefined &&
      before !== undefined &&
      templateSignature(before) !== templateSignature(detail);
    // The answer of a write IS the sheet's new detail: keep it, no second read. Without one the
    // detail is read again.
    if (detail)
      queryClient.setQueryData(specSheetDetailKey(documentId, sheetId), detail);
    else
      queryClient.invalidateQueries({
        queryKey: specSheetDetailKey(documentId, sheetId),
      });
    queryClient.invalidateQueries({ queryKey: specSheetListKey(documentId) });
    queryClient.invalidateQueries({
      queryKey: specSheetPreviewPrefix(documentId, sheetId),
      ...(switched ? { refetchType: 'none' as const } : {}),
    });
    queryClient.invalidateQueries({
      queryKey: [DESIGN_KEY, documentId, sheetId],
    });
  };

  const create = useMutation({
    mutationFn: (body: CreateSpecSheetBody) =>
      createSpecSheet(projectId, documentId, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: specSheetListKey(documentId) });
    },
  });

  const update = useMutation({
    mutationFn: ({
      sheetId,
      body,
    }: {
      sheetId: string;
      body: UpdateSpecSheetBody;
    }) => updateSpecSheet(projectId, documentId, sheetId, body),
    onSuccess: (detail, { sheetId }) => refreshSheet(sheetId, detail),
    onError: (error: Error) => toast.error(error.message),
  });

  const savePageEdit = useMutation({
    mutationFn: ({
      sheetId,
      key,
      layers,
    }: {
      sheetId: string;
      key: string;
      layers: TagLayer[];
    }) => saveSpecSheetPageEdit(projectId, documentId, sheetId, key, layers),
    onSuccess: (detail, { sheetId }) => refreshSheet(sheetId, detail),
    onError: (error: Error) => toast.error(error.message),
  });

  // The reader's autosave: one page's layers. The answer is the sheet's new detail and the page's
  // new layers are written into the cached preview chunk that holds it, so the still picture shows
  // them; nothing is invalidated, so nothing refetches (no loop while the designer is live).
  const autosavePage = useMutation({
    mutationFn: ({
      sheetId,
      key,
      layers,
    }: {
      sheetId: string;
      key: string;
      layers: TagLayer[];
    }) => saveSpecSheetPageEdit(projectId, documentId, sheetId, key, layers),
    onSuccess: (detail, { sheetId, key, layers }) => {
      if (detail)
        queryClient.setQueryData(
          specSheetDetailKey(documentId, sheetId),
          detail,
        );
      queryClient.setQueriesData<SpecSheetPreview>(
        { queryKey: specSheetPreviewPrefix(documentId, sheetId) },
        (old) => {
          if (!old || !old.doc || !Array.isArray(old.doc.sheets)) return old;
          const at = old.doc.sheets.findIndex(
            (sheet) => sheet.tags[0]?.request_tag_id === key,
          );
          if (at < 0) return old;
          const sheets = old.doc.sheets.map((sheet, i) =>
            i === at
              ? {
                  ...sheet,
                  tags: sheet.tags.map((tag, t) =>
                    t === 0 ? { ...tag, layers } : tag,
                  ),
                }
              : sheet,
          );
          return { ...old, doc: { ...old.doc, sheets } };
        },
      );
      queryClient.invalidateQueries({
        queryKey: specSheetListKey(documentId),
        refetchType: 'none',
      });
    },
  });

  // "Every page": the server changes the layer on every page that has it, so the previews are read
  // again (the live pages hold their own copy until they next mount).
  const applyAll = useMutation({
    mutationFn: ({
      sheetId,
      layerId,
      changes,
      originPageKey,
    }: {
      sheetId: string;
      layerId: string;
      changes: ApplyAllChanges;
      originPageKey?: string;
    }) =>
      applySpecSheetLayerToAll(
        projectId,
        documentId,
        sheetId,
        layerId,
        changes,
        originPageKey,
      ),
    onSuccess: async (detail, { sheetId }) => {
      if (detail)
        queryClient.setQueryData(
          specSheetDetailKey(documentId, sheetId),
          detail,
        );
      queryClient.invalidateQueries({
        queryKey: specSheetListKey(documentId),
        refetchType: 'none',
      });
      // Resolves once the previews are read again, so the live pages restart on the new layers.
      await queryClient.invalidateQueries({
        queryKey: specSheetPreviewPrefix(documentId, sheetId),
      });
    },
    onError: (error: Error) => toast.error(error.message),
  });

  // B6: a new element added to every page. The server changes the other pages, so the previews are
  // read again exactly as for `applyAll`.
  const addToAll = useMutation({
    mutationFn: ({
      sheetId,
      layer,
      originPageKey,
    }: {
      sheetId: string;
      layer: TagLayer;
      originPageKey?: string;
    }) => addSpecSheetLayerToAll(projectId, documentId, sheetId, layer, originPageKey),
    onSuccess: async (detail, { sheetId }) => {
      if (detail) queryClient.setQueryData(specSheetDetailKey(documentId, sheetId), detail);
      queryClient.invalidateQueries({ queryKey: specSheetListKey(documentId), refetchType: 'none' });
      await queryClient.invalidateQueries({ queryKey: specSheetPreviewPrefix(documentId, sheetId) });
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const exportPdf = useMutation({
    // A bare sheet id is a PDF (the sheets list); the reader also asks for PowerPoint.
    mutationFn: (target: string | { sheetId: string; format: 'pdf' | 'pptx' }) =>
      typeof target === 'string'
        ? queueSpecSheetPdf(projectId, documentId, target)
        : queueSpecSheetPdf(projectId, documentId, target.sheetId, target.format),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ENTITY_DOWNLOADS_QUERY_KEY });
      queryClient.invalidateQueries({ queryKey: MY_DOWNLOADS_QUERY_KEY });
      queryClient.invalidateQueries({ queryKey: specSheetListKey(documentId) });
      toast.success(
        'Preparing the spec sheet. It will appear in My Downloads.',
      );
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return { create, update, savePageEdit, autosavePage, applyAll, addToAll, exportPdf };
}
