import { useMutation, useQuery, useQueryClient, type QueryKey } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';
import type { ListPagerPage, ListPagerParams } from '@/hooks/useListPager';
import type { OcnWrite } from '@/types/orderChangeNotice';
import { isDeferredFormAction } from '@/app/(protected)/sla-management/_shared/formAction';
import {
  createOrderChangeNotice,
  decideOrderChangeNotice,
  getOrderChangeNotice,
  listChangeTypes,
  listOrderChangeNotices,
  listProjectOrderChangeNotices,
  markDone,
  reviseOrderChangeNotice,
  sendBack,
  sendForApproval,
  submitOrderChangeNotice,
  updateOrderChangeNotice,
  voidOrderChangeNotice,
  type OcnMoveResult,
  type OrderChangeNoticeListParams,
} from '../services/orderChangeNoticeService';

const LIST_KEY = 'order-change-notices';
const DETAIL_KEY = 'order-change-notice';

/** The list's React Query key; the detail pager rebuilds the SAME key from the URL. */
export function orderChangeNoticesListQueryKey(params: OrderChangeNoticeListParams): QueryKey {
  return [
    LIST_KEY,
    params.pageIndex,
    params.pageSize,
    params.sorting,
    params.searchQuery,
    params.status,
    params.changeTypeId,
    params.riskLevel,
  ];
}

function listParamsFromUrl(params: ListPagerParams): OrderChangeNoticeListParams {
  return {
    pageIndex: params.pageIndex,
    pageSize: params.pageSize,
    sorting: params.sorting,
    searchQuery: params.searchQuery,
    status: params.filters.status,
    changeTypeId: params.filters.change_type_id,
    riskLevel: params.filters.risk_level,
  };
}

/** The pager's two hooks into the list. */
export const orderChangeNoticesPagerQuery = {
  listQueryKey: (params: ListPagerParams): QueryKey =>
    orderChangeNoticesListQueryKey(listParamsFromUrl(params)),
  fetchPage: (params: ListPagerParams): Promise<ListPagerPage> =>
    listOrderChangeNotices(listParamsFromUrl(params)),
};

export function useOrderChangeNoticesQuery(params: OrderChangeNoticeListParams) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: orderChangeNoticesListQueryKey(params),
    queryFn: () => listOrderChangeNotices(params),
    // A failed read ends in the grid's Try again at once, not after a silent retry.
    retry: false,
  });
}

export function useProjectOrderChangeNoticesQuery(projectId: string | null | undefined) {
  return useQuery({
    queryKey: [LIST_KEY, 'project', projectId],
    queryFn: () => listProjectOrderChangeNotices(projectId as string),
    enabled: !!projectId,
    retry: false,
  });
}

export function useOrderChangeNoticeQuery(id: string | null | undefined) {
  return useQuery({
    queryKey: [DETAIL_KEY, id],
    queryFn: () => getOrderChangeNotice(id as string),
    enabled: !!id,
    retry: false,
  });
}

export function useChangeTypesQuery() {
  return useQuery({
    queryKey: [LIST_KEY, 'change-types'],
    queryFn: listChangeTypes,
    staleTime: 5 * 60_000,
  });
}

type Rev = { id: string; revisionNo: number };

export interface OrderChangeNoticeMutationOptions {
  /** A stage move was held for its grace window: the detail's `useFormAction().refresh`, so the
   *  shared countdown banner with its Undo appears (the purchase request detail's way). */
  onDeferred?: () => void;
}

export function useOrderChangeNoticeMutations(options: OrderChangeNoticeMutationOptions = {}) {
  const { onDeferred } = options;
  const queryClient = useQueryClient();
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: [LIST_KEY] });
    void queryClient.invalidateQueries({ queryKey: [DETAIL_KEY] });
  };
  const fail = (fallback: string) => (error: Error) => toast.error(error.message || fallback);
  /** `done` when the move applied; `held` while it waits out its grace window (nothing has
   *  happened yet, so no success is claimed: the banner shows the countdown and Undo). */
  const moved = (done: string, held: string) => (result: OcnMoveResult) => {
    refresh();
    if (isDeferredFormAction(result)) {
      onDeferred?.();
      toast.info(held);
      return;
    }
    queryClient.setQueryData([DETAIL_KEY, result.id], result);
    toast.success(done);
  };

  // Create and update report their own refusals in the form (beside the field), so no toast.
  const create = useMutation({
    mutationFn: (body: OcnWrite) => createOrderChangeNotice(body),
    onSuccess: refresh,
  });
  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: OcnWrite }) => updateOrderChangeNotice(id, body),
    onSuccess: refresh,
  });
  const submit = useMutation({
    mutationFn: ({ id, revisionNo }: Rev) => submitOrderChangeNotice(id, revisionNo),
    onSuccess: moved('Order change notice submitted', 'Submitting. You can still undo.'),
    onError: fail('Failed to submit the order change notice'),
  });
  const send = useMutation({
    mutationFn: ({ id, revisionNo }: Rev) => sendForApproval(id, revisionNo),
    onSuccess: moved('Sent for approval', 'Sending for approval. You can still undo.'),
    onError: fail('Failed to send the notice for approval'),
  });
  const back = useMutation({
    mutationFn: ({ id, revisionNo, reason }: Rev & { reason: string }) => sendBack(id, revisionNo, reason),
    onSuccess: moved('Sent back to the raiser', 'Sending back. You can still undo.'),
    onError: fail('Failed to send the notice back'),
  });
  const decide = useMutation({
    mutationFn: ({
      id,
      revisionNo,
      action,
      comments,
    }: Rev & { action: 'approved' | 'rejected'; comments: string | null }) =>
      decideOrderChangeNotice(id, revisionNo, action, comments),
    onSuccess: moved('Decision recorded', 'Recording the decision. You can still undo.'),
    onError: fail('Failed to record the decision'),
  });
  const done = useMutation({
    mutationFn: ({ id, revisionNo, csComment }: Rev & { csComment: string | null }) =>
      markDone(id, revisionNo, csComment),
    onSuccess: moved('Marked done', 'Marking done. You can still undo.'),
    onError: fail('Failed to mark the notice done'),
  });
  const voidIt = useMutation({
    mutationFn: ({ id, revisionNo, reason }: Rev & { reason: string }) =>
      voidOrderChangeNotice(id, revisionNo, reason),
    onSuccess: moved('Order change notice voided', 'Voiding. You can still undo.'),
    onError: fail('Failed to void the notice'),
  });
  const revise = useMutation({
    mutationFn: ({ id, revisionNo, reason }: Rev & { reason: string }) =>
      reviseOrderChangeNotice(id, revisionNo, reason),
    onSuccess: moved('Back to draft for changes', 'Revising. You can still undo.'),
    onError: fail('Failed to revise the notice'),
  });

  return { create, update, submit, send, back, decide, done, voidIt, revise };
}
