'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  approveLoadingPlan,
  buildContainerRequest,
  cancelLoadingPlan,
  createLoadingPlanRecord,
  createSpo,
  deleteSpo,
  downloadContainerRequestDocument,
  downloadSpoWorksheet,
  getConsolidatedPackingList,
  getContainerRequestHistory,
  getContainerSizes,
  getFulfilmentSuppliers,
  getLoadingPlanList,
  getPlanNotices,
  getSpoSuggestion,
  getSupplierNotices,
  getSupplierStock,
  getSupplierStockListFile,
  saveLoadingPlanEdits,
  sendContainerRequest,
  updateLoadingPlanCutOff,
  type ContainerRequestLine,
  type LoadingPlanCreate,
  type LoadingPlanListParams,
  type LoadingPlanRecord,
  type SpoConfirmLine,
} from '../services/fulfilmentService';

const KEY = ['scm', 'fulfilment'] as const;

const cold = { staleTime: 5 * 60_000, refetchOnWindowFocus: false, retry: 1 } as const;

export function useFulfilmentSuppliers() {
  // Wrapped (not passed bare): `getFulfilmentSuppliers` now takes an optional server-search
  // `query` (S8-followup) - react-query would otherwise call it with its own
  // QueryFunctionContext in that slot.
  return useQuery({
    queryKey: [...KEY, 'suppliers'],
    queryFn: () => getFulfilmentSuppliers(),
    ...cold,
  });
}

export function useContainerSizes() {
  return useQuery({ queryKey: [...KEY, 'container-sizes'], queryFn: getContainerSizes, ...cold });
}

export function useSupplierStock(supplierId: string | null) {
  return useQuery({
    queryKey: [...KEY, 'stock', supplierId],
    queryFn: () => getSupplierStock(supplierId as string),
    enabled: !!supplierId,
    refetchOnWindowFocus: false,
  });
}

/**
 * The plans list (`/scm/loading-plan`, R3). Server-paged, server-sorted and server-searched,
 * so the grid never holds more than the page it shows.
 */
export function useLoadingPlanList(params: LoadingPlanListParams) {
  return useQuery({
    queryKey: [...KEY, 'plan-list', params],
    queryFn: () => getLoadingPlanList(params),
    refetchOnWindowFocus: false,
    placeholderData: (prev) => prev,
  });
}

/** The stored copy of the supplier's own sheet - for the "View uploaded list" control. */
export function useSupplierStockListFile(supplierId: string | null) {
  return useQuery({
    queryKey: [...KEY, 'stock-list-file', supplierId],
    queryFn: () => getSupplierStockListFile(supplierId as string),
    enabled: !!supplierId,
    refetchOnWindowFocus: false,
  });
}

/** Invalidate everything keyed on one supplier: a new snapshot changes every plan under it. */
function useSupplierInvalidator() {
  const qc = useQueryClient();
  return (supplierId: string | null) => {
    void qc.invalidateQueries({ queryKey: [...KEY, 'stock', supplierId] });
    void qc.invalidateQueries({ queryKey: [...KEY, 'stock-list-file', supplierId] });
    void qc.invalidateQueries({ queryKey: [...KEY, 'plan-list'] });
  };
}

export function useStockListApplied() {
  return useSupplierInvalidator();
}

/** Start a plan (R4). No toast: the caller navigates straight onto the record. */
export function useCreateLoadingPlan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: LoadingPlanCreate) => createLoadingPlanRecord(body),
    onSuccess: () => void qc.invalidateQueries({ queryKey: [...KEY, 'plan-list'] }),
    onError: (e: Error) => toast.error(e.message),
  });
}

/** Cancel: the plan stops being worked on AND the supplier's live link stops answering (Q4). */
export function useCancelLoadingPlan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => cancelLoadingPlan(id),
    onSuccess: (plan: LoadingPlanRecord) => {
      qc.setQueryData([...KEY, 'container-request', plan.id], (prev: unknown) =>
        prev && typeof prev === 'object' ? { ...(prev as object), plan } : prev,
      );
      void qc.invalidateQueries({ queryKey: [...KEY, 'plan-list'] });
      void qc.invalidateQueries({ queryKey: [...KEY, 'container-request', plan.id] });
      toast.success('Plan cancelled. The supplier link no longer works.');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

/**
 * Save the typed quantities (R6). The whole map goes in one PUT, and the build is invalidated
 * rather than patched: `suggested_qty` comes back with the edits already applied, so the grid
 * and the document read the same numbers.
 */
export function useUpdateLoadingPlanCutOff(planId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (planHorizonDate: string | null) =>
      updateLoadingPlanCutOff(planId as string, planHorizonDate),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: [...KEY, 'container-request', planId] });
      void qc.invalidateQueries({ queryKey: [...KEY, 'plan-list'] });
      toast.success('Cut-off changed. The suggestion has been worked out again.');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useSaveLoadingPlanEdits(planId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (edits: Record<string, number>) =>
      saveLoadingPlanEdits(planId as string, edits),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: [...KEY, 'container-request', planId] });
      void qc.invalidateQueries({ queryKey: [...KEY, 'plan-list'] });
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

/** S8 - the notices produced by approving a plan, and the one action that produces them. */
export function usePlanNotices(planId: string | null) {
  return useQuery({
    queryKey: [...KEY, 'notices', planId],
    queryFn: () => getPlanNotices(planId as string),
    enabled: !!planId,
    refetchOnWindowFocus: false,
  });
}

export function useApproveLoadingPlan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (planId: string) => approveLoadingPlan(planId),
    onSuccess: (out, planId) => {
      qc.invalidateQueries({ queryKey: [...KEY, 'notices', planId] });
      // Say what actually happened per channel. "Notice sent" when the supplier has no address
      // on file would be the screen telling the user something untrue.
      const sent = out.notices.filter((n) => n.status === 'sent').length;
      if (sent) toast.success(`Notice sent on ${sent === 1 ? '1 channel' : `${sent} channels`}.`);
      else toast.warning('Notice created. No channel could send it, so send the document by hand.');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

/**
 * Stage 1 - the container request (PLAN-scm-loading-plan-demand-first.md). A pure read, so a
 * query the supplier picker drives directly - the same auto-fetch-on-select shape as
 * `useSupplierStock` / `useLoadingPlans` - rather than a mutation Ms Tee has to fire herself;
 * "Refresh suggestion" is this query's own `refetch`.
 *
 * `planHorizonDate` ("Plan until", captain 20 Aug) is keyed into the query so picking a
 * different cutoff is a fresh fetch, not a stale one served out of cache under the same key.
 */
export function useContainerRequestBuild(planId: string | null) {
  return useQuery({
    queryKey: [...KEY, 'container-request', planId],
    queryFn: () => buildContainerRequest(planId as string),
    enabled: !!planId,
    refetchOnWindowFocus: false,
    retry: false,
  });
}

/**
 * The sales history behind the rows currently ON SCREEN (AC-B8).
 *
 * Keyed on the product ids, so paging to the next 25 rows is a new query rather than a
 * refetch of everything: the sidecar exists precisely so a 120-product supplier does not pay
 * for 120 products' worth of monthly series to read one page.
 *
 * `cold` because a month bucket cannot change while she is looking at it - this is closed
 * history, not the live sales book.
 */
export function useContainerRequestHistory(supplierId: string | null, productIds: string[]) {
  // Sorted so two pages holding the same products in a different order share one cache entry.
  const key = [...productIds].sort().join(',');
  return useQuery({
    queryKey: [...KEY, 'container-request', 'history', supplierId, key],
    queryFn: () => getContainerRequestHistory(supplierId as string, productIds),
    enabled: !!supplierId && productIds.length > 0,
    ...cold,
  });
}

/** Every notice sent to this supplier, either stage - the caller filters by `notice_type`. */
export function useSupplierNotices(supplierId: string | null) {
  return useQuery({
    queryKey: [...KEY, 'notices', 'supplier', supplierId],
    queryFn: () => getSupplierNotices(supplierId as string),
    enabled: !!supplierId,
    refetchOnWindowFocus: false,
  });
}

export function useSendContainerRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      planId,
      lines,
    }: {
      planId: string;
      supplierId: string;
      supplierName: string;
      lines: ContainerRequestLine[];
    }) => sendContainerRequest(planId, lines),
    onSuccess: (_out, { planId, supplierId, supplierName }) => {
      void qc.invalidateQueries({ queryKey: [...KEY, 'notices', 'supplier', supplierId] });
      void qc.invalidateQueries({ queryKey: [...KEY, 'container-request', planId] });
      void qc.invalidateQueries({ queryKey: [...KEY, 'plan-list'] });
      toast.success(`Request sent to ${supplierName}.`);
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

/**
 * The gear menu's two downloads (R23): the same request, as a file, without sending it.
 *
 * A mutation rather than a query because it is an act she asks for and because the pending
 * state disables the menu item - there is nothing to cache, the answer is a file that has
 * already left for the disk.
 */
export function useDownloadContainerRequestDocument(planId: string | null) {
  return useMutation({
    mutationFn: ({
      lines,
      format,
    }: {
      lines: ContainerRequestLine[];
      format: 'xlsx' | 'pdf';
    }) => downloadContainerRequestDocument(planId as string, lines, format),
    onError: (e: Error) => toast.error(e.message),
  });
}

/** S10 - the consolidated packing list for one container, grouped by factory. */
export function useConsolidatedPackingList(shipmentId: string | null) {
  return useQuery({
    queryKey: [...KEY, 'packing-list', shipmentId],
    queryFn: () => getConsolidatedPackingList(shipmentId as string),
    enabled: !!shipmentId,
    refetchOnWindowFocus: false,
  });
}

/**
 * The SPO planner table (`PLAN-scm-proforma-to-spo.md`'s second amendment) - hoisted here so
 * the packing-list detail page's planner tab (`procurement-management/packing-lists/[id]`)
 * and any future caller share one cache key and one mutation shape, rather than each rolling
 * its own inline `useQuery`/`useMutation` the way the first cut's `CreateSpoPanel` did.
 */
export function useSpoSuggestion(shipmentId: string | null) {
  return useQuery({
    queryKey: [...KEY, 'spo-suggestion', shipmentId],
    queryFn: () => getSpoSuggestion(shipmentId as string),
    enabled: !!shipmentId,
    refetchOnWindowFocus: false,
  });
}

export function useCreateSpo(shipmentId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (lines: SpoConfirmLine[]) => createSpo(shipmentId as string, lines),
    onSuccess: (out) => {
      void qc.invalidateQueries({ queryKey: [...KEY, 'spo-suggestion', shipmentId] });
      const names = out.created_spos.map((s) => s.po_number).filter(Boolean).join(', ');
      const allocated = out.allocations.length;
      const allocatedMsg = allocated
        ? ` ${allocated} location${allocated === 1 ? '' : 's'} allocated.`
        : '';
      toast.success(
        out.created_spos.length
          ? `Created ${out.created_spos.length === 1 ? 'SPO' : `${out.created_spos.length} SPOs`}: ${names}.${allocatedMsg}`
          : 'Nothing was created - every line was already covered.',
      );
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

/** Delete action on the already-converted planner row (third amendment) - unwinds the whole
 *  conversion for this shipment. On success, the planner's own suggestion query is
 *  invalidated so it falls back to a normal (non-converted) `suggest` and re-renders the
 *  confirm table. */
export function useDeleteSpo(shipmentId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => deleteSpo(shipmentId as string),
    onSuccess: (out) => {
      void qc.invalidateQueries({ queryKey: [...KEY, 'spo-suggestion', shipmentId] });
      const names = out.deleted_po_numbers.join(', ');
      toast.success(
        out.deleted_spo_count === 1
          ? `Deleted SPO ${names}.`
          : `Deleted ${out.deleted_spo_count} SPOs: ${names}.`,
      );
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useDownloadSpoWorksheet(shipmentId: string | null) {
  return useMutation({
    mutationFn: (fallbackName?: string | null) =>
      downloadSpoWorksheet(shipmentId as string, fallbackName),
    onError: (e: Error) => toast.error(e.message),
  });
}
