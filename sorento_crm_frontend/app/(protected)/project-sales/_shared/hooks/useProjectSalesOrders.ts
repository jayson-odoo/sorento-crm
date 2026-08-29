'use client';

import { useMutation, useQuery, useQueryClient, type QueryKey } from '@tanstack/react-query';
import { toast } from 'sonner';
import { saveBlobAs } from '../services/fileDownload';
import { projectKey } from './useProjects';
import { allocationsKey } from './useProjectAllocations';
import { acknowledgeFinding, acknowledgeScheduleFinding, buildSalesOrders, bulkDeleteProjectSalesOrders, bulkSetLinesStockLocation, createAmendment, deleteProjectSalesOrder, downloadAmendmentAutocountChangeListXlsx, downloadSalesOrderImportFile, getAmendment, getAmendmentAutocountChangeList, getProjectSalesOrder, getSalesOrderWorksheet, listPoVersions, listProjectSalesOrders, listScheduleFindings, listScheduleVersions, previewAmendment, publishAmendment, publishSalesOrder, regroupSalesOrder, reorderSalesOrderLines, saveSalesOrderDocument, unpublishSalesOrder, updateAmendmentRowDecisions, updateSalesOrderLine } from '../services/projectSalesOrderService';
import type {
  AmendmentCreateBody,
  AmendmentDetail,
  AmendmentPreviewBody,
  AmendmentRowDecisionInput,
  ProjectSalesOrderDetail,
  ProjectSalesOrderListParams,
  SalesOrderDocumentSaveBody,
  SalesOrderLineUpdateBody,
  SalesOrderPublishBody,
  SalesOrderRegroupGroup,
  SalesOrderSplitBy,
} from '../types/projectSalesOrder.types';
import type { ListPagerParams, ListPagerPage } from '@/hooks/useListPager';

export const SALES_ORDERS_KEY = 'project-sales-orders';
export const SALES_ORDER_KEY = 'project-sales-order';
export const SALES_ORDER_WORKSHEET_KEY = 'project-sales-order-worksheet';
export const SCHEDULE_VERSIONS_KEY = 'project-schedule-versions';
export const SCHEDULE_FINDINGS_KEY = 'project-schedule-findings';
export const PO_VERSIONS_KEY = 'project-po-versions';
export const AMENDMENT_KEY = 'project-so-amendment';

export const salesOrdersKey = (projectId: string, params: ProjectSalesOrderListParams) => [
  SALES_ORDERS_KEY,
  projectId,
  params,
];
export const salesOrderKey = (psoId: string) => [SALES_ORDER_KEY, psoId];

/**
 * The list query a record URL describes, in the shape the list passes.
 *
 * The project sales orders list pages with 1-based `page`, so the URL's 0-based
 * `pageIndex` is converted here rather than at each call site.
 */
export function projectSalesOrdersListParamsFromUrl(
  params: ListPagerParams,
): ProjectSalesOrderListParams {
  return {
    page: params.pageIndex + 1,
    limit: params.pageSize,
    sort: params.sorting?.[0]?.id,
    dir: params.sorting?.[0]?.desc ? 'desc' : 'asc',
    query: params.searchQuery || undefined,
    status: params.filters.status,
    purchase_order_id: params.filters.purchase_order_id,
  };
}

/** The pager's two hooks into one project's sales orders list. */
export function projectSalesOrdersPagerQuery(projectId: string) {
  return {
    listQueryKey: (params: ListPagerParams): QueryKey =>
      salesOrdersKey(projectId, projectSalesOrdersListParamsFromUrl(params)),
    fetchPage: (params: ListPagerParams): Promise<ListPagerPage> =>
      listProjectSalesOrders(projectId, projectSalesOrdersListParamsFromUrl(params)),
  };
}

export function useProjectSalesOrders(
  projectId: string | undefined,
  params: ProjectSalesOrderListParams = {},
) {
  return useQuery({
    queryKey: salesOrdersKey(projectId ?? '', params),
    queryFn: () => listProjectSalesOrders(projectId as string, params),
    enabled: Boolean(projectId),
  });
}

export function useProjectSalesOrder(psoId: string | undefined) {
  return useQuery({
    queryKey: salesOrderKey(psoId ?? ''),
    queryFn: () => getProjectSalesOrder(psoId as string),
    enabled: Boolean(psoId),
  });
}


/**
 * The AutoCount worksheet for one order. Separate from the draft query rather than a field
 * on it: the worksheet is the document as AutoCount will read it, and it is only ever
 * wanted on its own screen.
 */
export function useSalesOrderWorksheet(psoId: string | undefined) {
  return useQuery({
    queryKey: [SALES_ORDER_WORKSHEET_KEY, psoId ?? ''],
    queryFn: () => getSalesOrderWorksheet(psoId as string),
    enabled: Boolean(psoId),
  });
}

export function useScheduleVersions(poId: string | undefined) {
  return useQuery({
    queryKey: [SCHEDULE_VERSIONS_KEY, poId],
    queryFn: () => listScheduleVersions(poId as string),
    enabled: Boolean(poId),
  });
}

export function usePoVersions(poId: string | undefined) {
  return useQuery({
    queryKey: [PO_VERSIONS_KEY, poId],
    queryFn: () => listPoVersions(poId as string),
    enabled: Boolean(poId),
  });
}

/**
 * The (PO, schedule) pair's own findings - a finding naming no PO line, so belonging to
 * no one order the pair drafted. Read alongside an order's detail page rather than
 * per-order, because it is the same list whichever sibling order is open.
 */
export function useScheduleFindings(
  poId: string | null | undefined,
  scheduleVersionId: string | null | undefined,
) {
  return useQuery({
    queryKey: [SCHEDULE_FINDINGS_KEY, poId, scheduleVersionId],
    queryFn: () => listScheduleFindings(poId as string, scheduleVersionId as string),
    enabled: Boolean(poId && scheduleVersionId),
  });
}

export function useAcknowledgeScheduleFinding(
  poId: string | null | undefined,
  scheduleVersionId: string | null | undefined,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ findingId, reason }: { findingId: string; reason: string }) =>
      acknowledgeScheduleFinding(poId as string, findingId, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: [SCHEDULE_FINDINGS_KEY, poId, scheduleVersionId],
      });
      toast.success('Reason recorded');
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

export function useAmendment(amendmentId: string | undefined) {
  return useQuery({
    queryKey: [AMENDMENT_KEY, amendmentId],
    queryFn: () => getAmendment(amendmentId as string),
    enabled: Boolean(amendmentId),
  });
}

/**
 * The AutoCount change list for an amendment (section 9.4): the accepted rows, in the
 * export's own order. Refetches whenever a decision changes the accepted set, because the
 * amendment query it is keyed alongside is what a decision invalidates.
 */
export function useAmendmentAutocountChangeList(amendmentId: string | undefined) {
  return useQuery({
    queryKey: [AMENDMENT_KEY, amendmentId, 'autocount-change-list'],
    queryFn: () => getAmendmentAutocountChangeList(amendmentId as string),
    enabled: Boolean(amendmentId),
  });
}

/**
 * Building is idempotent per (PO version, schedule version): it replaces the drafts it made
 * last time and leaves published ones alone, so the toast says how many drafts now stand
 * rather than "created".
 */
export function useSalesOrderBuild(projectId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      poId,
      scheduleVersionId,
      splitBy,
    }: {
      poId: string;
      scheduleVersionId: string;
      splitBy?: SalesOrderSplitBy;
    }) => buildSalesOrders(poId, scheduleVersionId, splitBy ?? 'area'),
    onSuccess: (envelope) => {
      queryClient.invalidateQueries({ queryKey: [SALES_ORDERS_KEY, projectId] });
      const count = envelope.data.length;
      const blocked = envelope.data.filter((row) => row.hard_findings > 0).length;
      toast.success(
        blocked > 0
          ? `${count} draft${count === 1 ? '' : 's'}, ${blocked} blocked`
          : `${count} draft${count === 1 ? '' : 's'} ready to review`,
      );
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

/**
 * Everything that writes to one draft. Each success refetches the draft itself AND the
 * project's list, because the list carries the finding counts and the status the user is
 * looking at on the other screen, AND the order's allocations, which the same detail page
 * shows per line and which a line edit can leave describing a line that no longer exists.
 */
export function useSalesOrderMutations(projectId: string, psoId: string) {
  const queryClient = useQueryClient();
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: salesOrderKey(psoId) });
    queryClient.invalidateQueries({ queryKey: [SALES_ORDERS_KEY, projectId] });
    queryClient.invalidateQueries({ queryKey: allocationsKey(psoId) });
  };

  const acknowledge = useMutation({
    mutationFn: ({ findingId, reason }: { findingId: string; reason: string }) =>
      acknowledgeFinding(psoId, findingId, reason),
    onSuccess: () => {
      invalidate();
      toast.success('Reason recorded');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  /**
   * The edit view's one write: the header and the whole line set together.
   *
   * No toast here. The detail screen raises exactly one ("Sales order saved") for the button
   * press, and a second notification for the same press is the noise the per-line saves were
   * taken out for.
   */
  const save = useMutation({
    mutationFn: (body: SalesOrderDocumentSaveBody) => saveSalesOrderDocument(psoId, body),
    onSuccess: () => invalidate(),
    onError: (error: Error) => toast.error(error.message),
  });

  const updateLine = useMutation({
    mutationFn: ({ lineId, body }: { lineId: string; body: SalesOrderLineUpdateBody }) =>
      updateSalesOrderLine(psoId, lineId, body),
    onSuccess: () => {
      invalidate();
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const regroup = useMutation({
    mutationFn: (groups: SalesOrderRegroupGroup[]) => regroupSalesOrder(psoId, groups),
    onSuccess: (envelope) => {
      invalidate();
      toast.success(
        `Re-split into ${envelope.data.length} sales order${envelope.data.length === 1 ? '' : 's'}`,
      );
    },
    onError: (error: Error) => toast.error(error.message),
  });

  // No toast: the publish dialog shows the reference and the import file itself, and it
  // renders a refusal (403 without the override, 422 without a reason) in place rather than
  // as a toast the user would have to read behind the dialog.
  const publish = useMutation({
    // The ordinary publish sends no body, not an empty one: the argument is only passed on
    // when there is an override to ask for.
    mutationFn: (body?: SalesOrderPublishBody) =>
      body ? publishSalesOrder(psoId, body) : publishSalesOrder(psoId),
    onSuccess: () => invalidate(),
  });

  /**
   * Back to draft, experimental (captain, 19 Aug 2026). The confirm dialog names the order
   * and states the consequence, so this raises no toast of its own beyond the error - the
   * 200 response speaks for itself once the status pill flips.
   */
  const unpublish = useMutation({
    mutationFn: () => unpublishSalesOrder(psoId),
    onSuccess: () => {
      invalidate();
      toast.success('Sales order returned to draft');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  /**
   * A hand drag: the row moves the instant it is dropped, before the server confirms it.
   * `onMutate` writes the new `line_no` order straight into the cached order so the table
   * never snaps back to the old position while the request is in flight; `onError` puts the
   * cached order back exactly as it was and says why. No success toast - the row landing
   * where it was dropped is the confirmation.
   */
  const reorderLines = useMutation({
    mutationFn: (lineIds: string[]) => reorderSalesOrderLines(psoId, lineIds),
    onMutate: async (lineIds: string[]) => {
      await queryClient.cancelQueries({ queryKey: salesOrderKey(psoId) });
      const previous = queryClient.getQueryData<ProjectSalesOrderDetail>(salesOrderKey(psoId));
      if (previous) {
        const byId = new Map(previous.lines.map((line) => [line.id, line]));
        const reordered = lineIds
          .map((id, index) => {
            const line = byId.get(id);
            return line ? { ...line, line_no: index + 1 } : null;
          })
          .filter((line): line is ProjectSalesOrderDetail['lines'][number] => line !== null);
        queryClient.setQueryData<ProjectSalesOrderDetail>(salesOrderKey(psoId), {
          ...previous,
          lines: reordered,
        });
      }
      return { previous };
    },
    onError: (error: Error, _lineIds, context) => {
      if (context?.previous) {
        queryClient.setQueryData(salesOrderKey(psoId), context.previous);
      }
      toast.error(error.message);
    },
    onSettled: () => invalidate(),
  });

  return { acknowledge, save, updateLine, regroup, publish, unpublish, reorderLines };
}

/**
 * One warehouse code on every line of one order, in one confirmed action.
 *
 * A standalone control rather than something staged inside the header's edit session: like
 * "Move lines" beside it, it acts immediately on the order as it is STORED, so it needs no
 * Save afterwards and works whether or not an edit session happens to be open.
 */
export function useBulkSetLinesStockLocation(projectId: string, psoId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ lineIds, stockLocation }: { lineIds: string[]; stockLocation: string | null }) =>
      bulkSetLinesStockLocation(psoId, lineIds, stockLocation),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: salesOrderKey(psoId) });
      queryClient.invalidateQueries({ queryKey: [SALES_ORDERS_KEY, projectId] });
      toast.success(
        `Stock location set on ${result.applied} line${result.applied === 1 ? '' : 's'}`,
      );
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

/**
 * Deleting one drafted sales order, so the build can be run again.
 *
 * The order's id is the MUTATION VARIABLE rather than a hook argument, because both callers
 * need it that way: the project's sales order list deletes whichever row was clicked, and the
 * detail page deletes the one it is showing. One implementation, so the two cannot invalidate
 * different things.
 *
 * `ConfirmDeleteDialog` raises the toast, so this one does not: it would be the second
 * notification for one press.
 */
export function useSalesOrderDelete(projectId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (psoId: string) => deleteProjectSalesOrder(psoId),
    onSuccess: (_result, psoId) => {
      queryClient.invalidateQueries({ queryKey: salesOrderKey(psoId) });
      queryClient.invalidateQueries({ queryKey: [SALES_ORDERS_KEY, projectId] });
      // The project row carries the funnel position and the last-activity stamp the list
      // reads, and a deleted draft changes both.
      queryClient.invalidateQueries({ queryKey: projectKey(projectId) });
    },
  });
}

/**
 * Deleting the drafts a reviewer has ticked, in one call.
 *
 * Invalidates exactly what the single delete does, plus one detail query per deleted id, so a
 * tab left open on one of them refetches into its own "could not be loaded" state rather than
 * showing an order that is gone.
 *
 * NO toast either way, and deliberately: `ConfirmDeleteDialog` raises both, and a second
 * notification for one button press is the noise the per-line saves were removed for. The
 * dialog's error toast is what carries the server's refusal sentence, which names every order
 * to un-tick.
 */
export function useSalesOrderBulkDelete(projectId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (ids: string[]) => bulkDeleteProjectSalesOrders(ids),
    onSuccess: (_result, ids) => {
      ids.forEach((psoId) =>
        queryClient.invalidateQueries({ queryKey: salesOrderKey(psoId) }),
      );
      queryClient.invalidateQueries({ queryKey: [SALES_ORDERS_KEY, projectId] });
      queryClient.invalidateQueries({ queryKey: projectKey(projectId) });
    },
  });
}

/**
 * The AutoCount import file for one order.
 *
 * A mutation rather than a query because it must only run when someone asks for the file,
 * and it caches nothing: the backend generates it per request so it always matches the
 * order as it stands. The variable is the reference the file is named after when the
 * response carries no filename of its own.
 */
export function useSalesOrderImportFile(psoId: string) {
  return useMutation({
    mutationFn: async (reference: string) => {
      const { blob, filename } = await downloadSalesOrderImportFile(psoId);
      saveBlobAs(blob, filename ?? `${reference}.csv`);
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

/**
 * The AutoCount change list workbook (section 9.4), same shape as the import file above: a
 * mutation because it must only run on request, and it caches nothing.
 */
export function useAmendmentAutocountChangeListExport(amendmentId: string) {
  return useMutation({
    mutationFn: async (reference: string) => {
      const { blob, filename } = await downloadAmendmentAutocountChangeListXlsx(amendmentId);
      saveBlobAs(blob, filename ?? `autocount-change-list-${reference}.xlsx`);
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

/**
 * Preview is a mutation rather than a query: it is a POST, it writes nothing, and it must
 * only run when the reviewer asks for a comparison.
 */
export function useAmendmentMutations(projectId: string, psoId: string) {
  const queryClient = useQueryClient();

  const preview = useMutation({
    mutationFn: (body: AmendmentPreviewBody) => previewAmendment(psoId, body),
    onError: (error: Error) => toast.error(error.message),
  });

  const create = useMutation({
    mutationFn: (body: AmendmentCreateBody) => createAmendment(psoId, body),
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: salesOrderKey(psoId) });
      queryClient.invalidateQueries({ queryKey: [SALES_ORDERS_KEY, projectId] });
      toast.success(`Amendment proposed. Change notice ${created.ocn_number} awaits approval.`);
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const publish = useMutation({
    mutationFn: (amendmentId: string) => publishAmendment(amendmentId),
    onSuccess: (amendment) => {
      queryClient.invalidateQueries({ queryKey: salesOrderKey(psoId) });
      queryClient.invalidateQueries({ queryKey: [SALES_ORDERS_KEY, projectId] });
      queryClient.invalidateQueries({ queryKey: [AMENDMENT_KEY, amendment.id] });
      toast.success('Amendment published');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  /**
   * Accept or decline one row (section 9.3). Applied to the cached amendment OPTIMISTICALLY
   * - a segmented control that waited out a round trip before flipping reads as broken - and
   * rolled back if the server refuses (a decline with no reason, or a published amendment).
   * The change list is invalidated alongside: which rows are accepted is exactly what it
   * lists.
   */
  const updateRowDecisions = useMutation({
    mutationFn: ({
      amendmentId,
      decisions,
    }: {
      amendmentId: string;
      decisions: Record<string, AmendmentRowDecisionInput>;
    }) => updateAmendmentRowDecisions(amendmentId, decisions),
    onMutate: async ({ amendmentId, decisions }) => {
      const key = [AMENDMENT_KEY, amendmentId];
      await queryClient.cancelQueries({ queryKey: key });
      const previous = queryClient.getQueryData<AmendmentDetail>(key);
      if (previous) {
        queryClient.setQueryData<AmendmentDetail>(key, {
          ...previous,
          rows: previous.rows.map((row) => {
            const rowKey = row.row_key ?? `${row.so_line_id}:${row.field}`;
            const patch = decisions[rowKey];
            if (!patch) return row;
            return {
              ...row,
              decision: patch.decision,
              declined_reason: patch.decision === 'declined' ? (patch.reason ?? null) : null,
            };
          }),
        });
      }
      return { previous };
    },
    onError: (error: Error, variables, context) => {
      if (context?.previous) {
        queryClient.setQueryData([AMENDMENT_KEY, variables.amendmentId], context.previous);
      }
      toast.error(error.message);
    },
    onSuccess: (amendment) => {
      queryClient.setQueryData([AMENDMENT_KEY, amendment.id], amendment);
      queryClient.invalidateQueries({
        queryKey: [AMENDMENT_KEY, amendment.id, 'autocount-change-list'],
      });
    },
  });

  return { preview, create, publish, updateRowDecisions };
}
