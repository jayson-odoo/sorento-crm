'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  approveLoadingPlan,
  buildContainerRequest,
  createLoadingPlan,
  createSpo,
  deleteLoadingPlan,
  deleteSpo,
  downloadSpoWorksheet,
  getConsolidatedPackingList,
  getContainerSizes,
  getFulfilmentSuppliers,
  getLoadingPlan,
  getLoadingPlans,
  getPlanNotices,
  getSpoSuggestion,
  getSupplierNotices,
  getSupplierStock,
  getSupplierStockListFile,
  getUnfinishedStock,
  sendContainerRequest,
  updateLoadingPlan,
  type ContainerRequestLine,
  type LoadingPlan,
  type LoadingPlanRequest,
  type SpoConfirmLine,
} from '../services/fulfilmentService';
import { fmtTrimmedDecimal } from '../lib/format';

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

export function useUnfinishedStock(supplierId: string | null) {
  return useQuery({
    queryKey: [...KEY, 'unfinished', supplierId],
    queryFn: () => getUnfinishedStock(supplierId as string),
    enabled: !!supplierId,
    refetchOnWindowFocus: false,
  });
}

export function useLoadingPlans(supplierId: string | null) {
  return useQuery({
    queryKey: [...KEY, 'plans', supplierId],
    queryFn: () => getLoadingPlans(supplierId ?? undefined),
    enabled: !!supplierId,
    refetchOnWindowFocus: false,
  });
}

export function useLoadingPlanDetail(planId: string | null) {
  return useQuery({
    queryKey: [...KEY, 'plan', planId],
    queryFn: () => getLoadingPlan(planId as string),
    enabled: !!planId,
    refetchOnWindowFocus: false,
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
    void qc.invalidateQueries({ queryKey: [...KEY, 'unfinished', supplierId] });
    void qc.invalidateQueries({ queryKey: [...KEY, 'plans', supplierId] });
    void qc.invalidateQueries({ queryKey: [...KEY, 'stock-list-file', supplierId] });
  };
}

export function useStockListApplied() {
  return useSupplierInvalidator();
}

export function useBuildLoadingPlan() {
  const invalidate = useSupplierInvalidator();
  return useMutation({
    mutationFn: (body: LoadingPlanRequest) => createLoadingPlan(body),
    onSuccess: (plan: LoadingPlan) => {
      invalidate(plan.supplier_id);
      toast.success(
        `Planned ${fmtTrimmedDecimal(plan.planned_cbm, 3)} of ${fmtTrimmedDecimal(plan.capacity_cbm, 3)} cbm.`,
      );
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useRerunLoadingPlan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string; container_count?: number; container_type?: string }) =>
      updateLoadingPlan(id, body),
    onSuccess: (plan: LoadingPlan) => {
      qc.setQueryData([...KEY, 'plan', plan.id], plan);
      void qc.invalidateQueries({ queryKey: [...KEY, 'plans', plan.supplier_id] });
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useDeleteLoadingPlan(supplierId: string | null) {
  const invalidate = useSupplierInvalidator();
  return useMutation({
    mutationFn: (id: string) => deleteLoadingPlan(id),
    onSuccess: () => {
      invalidate(supplierId);
      toast.success('Loading plan deleted.');
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
export function useContainerRequestBuild(
  supplierId: string | null,
  planHorizonDate?: string | null,
) {
  return useQuery({
    queryKey: [...KEY, 'container-request', supplierId, planHorizonDate ?? null],
    queryFn: () => buildContainerRequest(supplierId as string, planHorizonDate),
    enabled: !!supplierId,
    refetchOnWindowFocus: false,
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
      supplierId,
      lines,
    }: {
      supplierId: string;
      supplierName: string;
      lines: ContainerRequestLine[];
    }) => sendContainerRequest(supplierId, lines),
    onSuccess: (_out, { supplierId, supplierName }) => {
      void qc.invalidateQueries({ queryKey: [...KEY, 'notices', 'supplier', supplierId] });
      toast.success(`Request sent to ${supplierName}.`);
    },
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
