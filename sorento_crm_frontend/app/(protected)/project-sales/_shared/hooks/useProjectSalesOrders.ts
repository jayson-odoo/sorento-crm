'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  useRecordNeighbours,
  type RecordNeighboursResult,
} from '@/hooks/useRecordNeighbours';
import { saveBlobAs } from '../services/fileDownload';
import { projectKey } from './useProjects';
import { allocationsKey } from './useProjectAllocations';
import {
  acknowledgeFinding,
  buildSalesOrders,
  bulkDeleteProjectSalesOrders,
  createAmendment,
  deleteProjectSalesOrder,
  downloadAmendmentAutocountChangeListXlsx,
  downloadSalesOrderImportFile,
  getAmendment,
  getAmendmentAutocountChangeList,
  getProjectSalesOrder,
  getSalesOrderWorksheet,
  listPoVersions,
  listProjectSalesOrders,
  listScheduleVersions,
  previewAmendment,
  publishAmendment,
  publishSalesOrder,
  regroupSalesOrder,
  salesOrderNeighboursPath,
  saveSalesOrderDocument,
  updateAmendmentRowDecisions,
  updateSalesOrderLine,
} from '../services/projectSalesOrderService';
import type {
  AmendmentCreateBody,
  AmendmentDetail,
  AmendmentPreviewBody,
  AmendmentRowDecisionInput,
  ProjectSalesOrderListParams,
  SalesOrderDocumentSaveBody,
  SalesOrderLineUpdateBody,
  SalesOrderPublishBody,
  SalesOrderRegroupGroup,
  SalesOrderSplitBy,
} from '../types/projectSalesOrder.types';

export const SALES_ORDERS_KEY = 'project-sales-orders';
export const SALES_ORDER_KEY = 'project-sales-order';
export const SALES_ORDER_WORKSHEET_KEY = 'project-sales-order-worksheet';
export const SCHEDULE_VERSIONS_KEY = 'project-schedule-versions';
export const PO_VERSIONS_KEY = 'project-po-versions';
export const AMENDMENT_KEY = 'project-so-amendment';

export const salesOrdersKey = (projectId: string, params: ProjectSalesOrderListParams) => [
  SALES_ORDERS_KEY,
  projectId,
  params,
];
export const salesOrderKey = (psoId: string) => [SALES_ORDER_KEY, psoId];

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
 * Prev/next within the project's sales orders, so a reviewer can walk them one by one
 * rather than going back to the list between each.
 *
 * No list params are sent: the detail page is reached from a tab rather than from a
 * filtered grid, so the sequence is the project's own default order (newest first), which
 * is what the tab shows.
 */
export function useProjectSalesOrderNeighbours(
  projectId: string | undefined,
  psoId: string | undefined,
): RecordNeighboursResult {
  return useRecordNeighbours(
    salesOrderNeighboursPath(projectId ?? ''),
    projectId ? (psoId ?? null) : null,
  );
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

  return { acknowledge, save, updateLine, regroup, publish };
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
