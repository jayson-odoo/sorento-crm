'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { useUploadActivity } from '@/components/upload-activity/useUploadActivity';
import {
  acknowledgeOrderInquiryRows,
  acknowledgeOrderInquiryRowsByFilter,
  autoPlaceOrderInquiryRows,
  getOrderInquiryPoCandidates,
  getOrderInquiryUploadJob,
  getOrderInquiryPoDetail,
  getOrderInquirySpoDetail,
  getOrderInquirySummary,
  getOrderInquiryWorklistSummary,
  getSalesOrderInquiry,
  getUnplaceAllPreview,
  listOrderInquiryRows,
  linkNowOrderInquiryRows,
  listOrderInquiryWorklist,
  markOrderInquiryRows,
  rejectOrderInquiryRow,
  rejectOrderInquiryRows,
  placeOrderInquiryRowOnPo,
  placeOrderInquiryRowOnPoAllocations,
  unacknowledgeOrderInquiryRows,
  unplaceAllOrderInquiryRows,
  unplaceOrderInquiryRow,
} from '../services/orderInquiryService';
import { getOrderInquiryMatrix } from '../services/orderInquiryMatrixService';
import { PLANNING_BOARD_KEY } from './useFulfilmentPlanning';
import type { LinkHorizonRequest } from '../lib/linkHorizon';
import { acknowledgeOutcomeText, linkOutcomeText } from '../lib/linkHorizon';
import type {
  AutoPlaceRequest,
  OrderInquiryListParams,
  OrderInquiryMatrixParams,
  OrderInquiryPoAllocation,
  OrderInquiryWorklistParams,
  UnplaceAllRequest,
} from '../types/orderInquiry.types';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';

export const ORDER_INQUIRY_ROWS_KEY = 'project-order-inquiry-rows';
export const ORDER_INQUIRY_SUMMARY_KEY = 'project-order-inquiry-summary';
export const ORDER_INQUIRY_KEY = 'project-order-inquiry';
export const ORDER_INQUIRY_WORKLIST_KEY = 'order-inquiry-worklist';
export const ORDER_INQUIRY_WORKLIST_SUMMARY_KEY = 'order-inquiry-worklist-summary';
export const ORDER_INQUIRY_PO_CANDIDATES_KEY = 'order-inquiry-po-candidates';
export const ORDER_INQUIRY_PO_DETAIL_KEY = 'order-inquiry-po-detail';
export const ORDER_INQUIRY_SPO_DETAIL_KEY = 'order-inquiry-spo-detail';
export const ORDER_INQUIRY_UNPLACE_ALL_PREVIEW_KEY = 'order-inquiry-unplace-all-preview';
export const ORDER_INQUIRY_UPLOAD_JOB_KEY = 'order-inquiry-upload-job';
export const ORDER_INQUIRY_MATRIX_KEY = 'order-inquiry-matrix';

export const orderInquiryRowsKey = (
  projectId: string,
  params: OrderInquiryListParams,
) => [ORDER_INQUIRY_ROWS_KEY, projectId, params];

export function useOrderInquiryRows(
  projectId: string | undefined,
  params: OrderInquiryListParams = {},
) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: orderInquiryRowsKey(projectId ?? '', params),
    queryFn: () => listOrderInquiryRows(projectId as string, params),
    enabled: Boolean(projectId),
  });
}

export function useOrderInquirySummary(projectId: string | undefined) {
  return useQuery({
    queryKey: [ORDER_INQUIRY_SUMMARY_KEY, projectId],
    queryFn: () => getOrderInquirySummary(projectId as string),
    enabled: Boolean(projectId),
  });
}

/**
 * Purchasing's own worklist: every raised row, across every project AND every adopted
 * AutoCount order, which belongs to no project and is therefore reachable nowhere else.
 *
 * `enabled` lets a caller hold the request off until it is actually needed - the
 * calendar view's day drilldown, for one, has nothing to ask for until a day is picked.
 */
export function useOrderInquiryWorklist(
  params: OrderInquiryWorklistParams = {},
  options: { enabled?: boolean } = {},
) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: [ORDER_INQUIRY_WORKLIST_KEY, params],
    queryFn: () => listOrderInquiryWorklist(params),
    enabled: options.enabled,
    // Every filter and every page is a new key, so without this the grid empties itself
    // between the press and the answer and the page jumps under the cursor.
  });
}

/**
 * The month strip and the state counts.
 *
 * Sent WITH the month filter, because the strip's totals are the visible month's. The
 * month AXIS (`by_month`) is the one thing the server computes ignoring that filter, so
 * the control that changes month never empties itself.
 */
export function useOrderInquiryWorklistSummary(
  params: OrderInquiryWorklistParams = {},
  options: { enabled?: boolean } = {},
) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: [ORDER_INQUIRY_WORKLIST_SUMMARY_KEY, params],
    queryFn: () => getOrderInquiryWorklistSummary(params),
    enabled: options.enabled,
    // Above all here: the month strip is inside this answer, so without it pressing a
    // month makes the control you just used vanish until the next answer lands.
  });
}

/**
 * The Schedule matrix's own read (S3): the same filters as the list, plus which axis and
 * which date cut. Server-side GROUP BY in Phase 2; a small in-process fixture in Phase 1
 * (`orderInquiryMatrixService`) - the caller never has to know which.
 */
export function useOrderInquiryMatrix(
  params: OrderInquiryMatrixParams,
  options: { enabled?: boolean } = {},
) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: [ORDER_INQUIRY_MATRIX_KEY, params],
    queryFn: () => getOrderInquiryMatrix(params),
    enabled: options.enabled,
  });
}

/**
 * "Unplace all"'s own count for the toolbar button and its confirm dialog - the CURRENT
 * worklist scope (the SAME filters the list itself reads), resolved server-side so it is
 * right regardless of how many pages the matching set actually spans. Kept live the same
 * way the month strip is: it has to go to zero the instant the last placed row in scope
 * is dealt with, or the button stays clickable on an empty scope.
 */
export function useUnplaceAllPreview(
  filters: UnplaceAllRequest = {},
  options: { enabled?: boolean } = {},
) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: [ORDER_INQUIRY_UNPLACE_ALL_PREVIEW_KEY, filters],
    queryFn: () => getUnplaceAllPreview(filters),
    enabled: options.enabled,
  });
}

export function useSalesOrderInquiry(psoId: string | undefined) {
  return useQuery({
    queryKey: [ORDER_INQUIRY_KEY, psoId],
    queryFn: () => getSalesOrderInquiry(psoId as string),
    enabled: Boolean(psoId),
    // A sales order that has not published yet has no inquiry, and 404 is the honest
    // answer rather than a failure worth retrying.
    retry: false,
  });
}

/**
 * Marking rows refetches the rows AND the summary: the header count is the thing that
 * tells purchasing how much of this project is still open, and a stale one is worse than
 * no count at all.
 */
export function useOrderInquiryMutations(projectId: string) {
  const queryClient = useQueryClient();

  const mark = useMutation({
    mutationFn: ({ rowIds, state }: { rowIds: string[]; state: string }) =>
      markOrderInquiryRows(rowIds, state),
    onSuccess: (rows, variables) => {
      queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_ROWS_KEY, projectId] });
      queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_SUMMARY_KEY, projectId] });
      queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_KEY] });
      const count = rows.length;
      const said =
        variables.state === 'actioned'
          ? 'marked as actioned'
          : variables.state === 'cancelled'
            ? 'cancelled'
            : 'reopened';
      toast.success(`${count} row${count === 1 ? '' : 's'} ${said}`);
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return { mark };
}

/** Candidates for one row's "Place on PO" dialog (section G), fetched only while it is
 * open - `enabled` lets the caller hold the request off until the dialog mounts. */
export function useOrderInquiryPoCandidates(
  rowId: string | undefined,
  options: { enabled?: boolean } = {},
) {
  return useQuery({
    queryKey: [ORDER_INQUIRY_PO_CANDIDATES_KEY, rowId],
    queryFn: () => getOrderInquiryPoCandidates(rowId as string),
    enabled: Boolean(rowId) && options.enabled !== false,
  });
}

/** The document lightbox's PO half: that purchase order's header, every line and who
 * holds its quantity. Fetched only while the dialog is open - `enabled` holds the
 * request off until then. */
export function useOrderInquiryPoDetail(
  poId: string | undefined,
  options: { enabled?: boolean } = {},
) {
  return useQuery({
    queryKey: [ORDER_INQUIRY_PO_DETAIL_KEY, poId],
    queryFn: () => getOrderInquiryPoDetail(poId as string),
    enabled: Boolean(poId) && options.enabled !== false,
  });
}

/** The same lightbox's SPO half, addressed by the shipping order's own number. */
export function useOrderInquirySpoDetail(
  spoNumber: string | undefined,
  options: { enabled?: boolean } = {},
) {
  return useQuery({
    queryKey: [ORDER_INQUIRY_SPO_DETAIL_KEY, spoNumber],
    queryFn: () => getOrderInquirySpoDetail(spoNumber as string),
    enabled: Boolean(spoNumber) && options.enabled !== false,
    // A shipping order the endpoint cannot answer for is an empty state, not something
    // to ask for three more times.
    retry: false,
  });
}

/**
 * Place on PO / Unplace (section G). Not scoped to a project id: the per-project screen
 * and purchasing's cross-project worklist carry the same row action, so both invalidate
 * every query family a placement touches rather than just their own screen's.
 */
export function useOrderInquiryPlacementMutations() {
  const queryClient = useQueryClient();

  function invalidateAfterPlacement() {
    queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_ROWS_KEY] });
    queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_SUMMARY_KEY] });
    queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_KEY] });
    queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_WORKLIST_KEY] });
    queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_WORKLIST_SUMMARY_KEY] });
    // Another raised row on the same product may now cover less (or more) of the
    // document line this one just linked or freed.
    queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_PO_CANDIDATES_KEY] });
    // A single link/unlink moves the linked count "Unlink all" reads too.
    queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_UNPLACE_ALL_PREVIEW_KEY] });
  }

  const place = useMutation({
    mutationFn: ({ rowId, poLineId }: { rowId: string; poLineId: string }) =>
      placeOrderInquiryRowOnPo(rowId, poLineId),
    onSuccess: () => {
      invalidateAfterPlacement();
      toast.success('Linked');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  /**
   * The cascade shape: one or more `{po_line_id | spo_allocation_id, qty}` lines in one
   * call. SET semantics (S8, AC-CF-25): the submission becomes the row's whole link
   * set - a line the row held that is missing from it is retired (unless
   * `offeredLineIds` says the caller never saw it), a resubmitted line is adjusted, and
   * a new line is linked.
   */
  const placeAllocations = useMutation({
    mutationFn: ({
      rowId,
      allocations,
      offeredLineIds,
    }: {
      rowId: string;
      allocations: OrderInquiryPoAllocation[];
      offeredLineIds?: string[];
    }) => placeOrderInquiryRowOnPoAllocations(rowId, allocations, offeredLineIds),
    onSuccess: () => {
      invalidateAfterPlacement();
      toast.success('Linked');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  /** Unlink: one link when `linkId` names it, every link the row holds when it does not. */
  const unplace = useMutation({
    mutationFn: ({ rowId, linkId }: { rowId: string; linkId?: string }) =>
      unplaceOrderInquiryRow(rowId, linkId),
    onSuccess: () => {
      invalidateAfterPlacement();
      toast.success('Unlinked');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return { place, placeAllocations, unplace };
}

/**
 * Run the cascade now - the worklist's "Auto-link". Invalidates the same query families a
 * single link does, since a bulk pass can touch any of them.
 */
export function useAutoPlaceOrderInquiryRows() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: AutoPlaceRequest = {}) => autoPlaceOrderInquiryRows(params),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_ROWS_KEY] });
      queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_SUMMARY_KEY] });
      queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_KEY] });
      queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_WORKLIST_KEY] });
      queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_WORKLIST_SUMMARY_KEY] });
      queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_PO_CANDIDATES_KEY] });
      queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_UNPLACE_ALL_PREVIEW_KEY] });
      toast.success(linkOutcomeText(result));
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

/**
 * "Unlink all" for the CURRENT worklist scope (the captain, 20-21 Aug): every linked or
 * partly linked row matching the filters passed in loses its links, ready for a clean
 * Auto-link re-deal. Named after its route, which the plan deliberately left unrenamed.
 */
export function useUnplaceAllOrderInquiryRows() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params: UnplaceAllRequest = {}) => unplaceAllOrderInquiryRows(params),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_ROWS_KEY] });
      queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_SUMMARY_KEY] });
      queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_KEY] });
      queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_WORKLIST_KEY] });
      queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_WORKLIST_SUMMARY_KEY] });
      queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_PO_CANDIDATES_KEY] });
      queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_UNPLACE_ALL_PREVIEW_KEY] });
      toast.success(
        `${result.unplaced} row${result.unplaced === 1 ? '' : 's'} unlinked`,
      );
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

/**
 * The upload this page queued, watched to its end (AC-H13).
 *
 * The drawer's own feed is the watcher - one poll for every upload in the system, already
 * running - so this reads the session whose id is the job's rather than starting a second
 * one. `landed` is the moment the worker is done with it, whichever way it ended; only
 * then is the job asked what it wrote, because before then the answer is half a book.
 *
 * A job the feed has never heard of reads as still running: it was queued a moment ago and
 * the feed has not caught up, and offering to link against a book nobody has read yet is
 * the thing this gate exists to stop.
 */
export function useUploadedBook(jobId: string | null) {
  const { sessions } = useUploadActivity();
  const session = jobId
    ? sessions.find((s) => s.session_id === jobId || s.import_job_id === jobId)
    : undefined;
  const landed = Boolean(
    session && session.status !== 'uploading' && session.status !== 'processing',
  );

  const scope = useQuery({
    queryKey: [ORDER_INQUIRY_UPLOAD_JOB_KEY, jobId],
    queryFn: () => getOrderInquiryUploadJob(jobId as string),
    enabled: Boolean(jobId) && landed,
    // The job is terminal by now, so its answer cannot change; a refetch on every focus
    // would ask the same question again for the life of the alert.
    staleTime: Infinity,
    retry: false,
  });

  return { landed, failed: session?.status === 'failed', scope: scope.data ?? null };
}

/**
 * The handshake (`PLAN-scm-oi-handshake.md`): Acknowledge, Reject, Link now.
 *
 * All three invalidate the same families a link does, because all three MOVE links:
 * acknowledging runs the cascade for the rows it takes on, rejecting takes a row out of
 * netting (and its line back to the board), and Link now is the cascade itself.
 */
export function useOrderInquiryHandshake() {
  const queryClient = useQueryClient();

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_ROWS_KEY] });
    queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_SUMMARY_KEY] });
    queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_KEY] });
    queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_WORKLIST_KEY] });
    queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_WORKLIST_SUMMARY_KEY] });
    queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_PO_CANDIDATES_KEY] });
    queryClient.invalidateQueries({ queryKey: [ORDER_INQUIRY_UNPLACE_ALL_PREVIEW_KEY] });
  }

  const acknowledge = useMutation({
    // `horizon` is the LINK HORIZON the cascade half of the press runs under (AC-LH1):
    // every ticked row is taken on, and one due after that date is left Not linked and
    // reported back as "N after <date>". `linkHorizonRequest` builds it, so this press and
    // the other three say the same thing about the same date (S1).
    //
    // `filter` is the worklist's own "Select all N matching" (PLAN-oi-confirm-per-so,
    // AC-CF-7): the CURRENT worklist scope rather than a client-built id list, for a
    // selection that spans more pages than were ever loaded. Mutually exclusive with
    // `rowIds` on the wire - the caller sends exactly one.
    mutationFn: ({
      rowIds,
      filter,
      horizon,
    }: {
      rowIds?: string[];
      filter?: OrderInquiryWorklistParams;
      horizon?: LinkHorizonRequest;
    }) =>
      filter
        ? acknowledgeOrderInquiryRowsByFilter(filter, horizon)
        : acknowledgeOrderInquiryRows(rowIds ?? [], horizon),
    onSuccess: (result) => {
      invalidate();
      toast.success(acknowledgeOutcomeText(result));
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const reject = useMutation({
    mutationFn: ({ rowId, reason }: { rowId: string; reason: string }) =>
      rejectOrderInquiryRow(rowId, reason),
    onSuccess: () => {
      invalidate();
      // The board is where the line went back to, so its own reads are stale now.
      queryClient.invalidateQueries({ queryKey: [PLANNING_BOARD_KEY] });
      toast.success('Rejected. The line is back with CS.');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  /**
   * The same refusal, for a batch, with ONE reason (item 15). Reject moved into the
   * Actions menu when the row actions column went, so the reason is asked for once and
   * carried onto every ticked row.
   */
  const rejectRows = useMutation({
    mutationFn: ({ rowIds, reason }: { rowIds: string[]; reason: string }) =>
      rejectOrderInquiryRows(rowIds, reason),
    onSuccess: (result) => {
      invalidate();
      queryClient.invalidateQueries({ queryKey: [PLANNING_BOARD_KEY] });
      const failed = (result.results ?? []).filter((entry) => !entry.ok).length;
      const rows = `${result.rejected} row${result.rejected === 1 ? '' : 's'} rejected`;
      if (failed > 0) toast.warning(`${rows}, ${failed} could not be`);
      else toast.success(`${rows}. The lines are back with CS.`);
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const linkNow = useMutation({
    mutationFn: (params: AutoPlaceRequest = {}) => linkNowOrderInquiryRows(params),
    onSuccess: (result) => {
      invalidate();
      toast.success(linkOutcomeText(result));
    },
    onError: (error: Error) => toast.error(error.message),
  });

  // PLAN-oi-worklist-split-customer-project.md, owner 18 Sep 2026: reversible (a plain Confirm undoes
  // it), so it invalidates the same families Confirm does and asks for no confirmation
  // dialog of its own.
  const unacknowledge = useMutation({
    mutationFn: (rowIds: string[]) => unacknowledgeOrderInquiryRows(rowIds),
    onSuccess: (result) => {
      invalidate();
      const rows = `${result.updated} row${result.updated === 1 ? '' : 's'}`;
      // N4 (review round 1): the same warn/success split `rejectRows` above uses for a
      // partial outcome - a batch that skipped something is not silently the same as
      // one that did not.
      if (result.skipped > 0) {
        toast.warning(`${rows} back to To confirm, ${result.skipped} skipped`);
      } else {
        toast.success(`${rows} back to To confirm`);
      }
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return { acknowledge, reject, rejectRows, linkNow, unacknowledge };
}
