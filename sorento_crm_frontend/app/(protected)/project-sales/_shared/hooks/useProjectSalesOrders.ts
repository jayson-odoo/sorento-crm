'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { saveBlobAs } from '../services/fileDownload';
import {
  acknowledgeFinding,
  buildSalesOrders,
  createAmendment,
  downloadSalesOrderImportFile,
  getAmendment,
  getProjectSalesOrder,
  getSalesOrderWorksheet,
  listPoVersions,
  listProjectSalesOrders,
  listScheduleVersions,
  previewAmendment,
  publishAmendment,
  publishSalesOrder,
  regroupSalesOrder,
  updateSalesOrderLine,
} from '../services/projectSalesOrderService';
import type {
  AmendmentCreateBody,
  AmendmentPreviewBody,
  ProjectSalesOrderListParams,
  SalesOrderLineUpdateBody,
  SalesOrderRegroupGroup,
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
 * Building is idempotent per (PO version, schedule version): it replaces the drafts it made
 * last time and leaves published ones alone, so the toast says how many drafts now stand
 * rather than "created".
 */
export function useSalesOrderBuild(projectId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ poId, scheduleVersionId }: { poId: string; scheduleVersionId: string }) =>
      buildSalesOrders(poId, scheduleVersionId),
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
 * looking at on the other screen.
 */
export function useSalesOrderMutations(projectId: string, psoId: string) {
  const queryClient = useQueryClient();
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: salesOrderKey(psoId) });
    queryClient.invalidateQueries({ queryKey: [SALES_ORDERS_KEY, projectId] });
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

  // No toast: the publish dialog shows the reference and the import file itself.
  const publish = useMutation({
    mutationFn: () => publishSalesOrder(psoId),
    onSuccess: () => invalidate(),
  });

  return { acknowledge, updateLine, regroup, publish };
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

  return { preview, create, publish };
}
