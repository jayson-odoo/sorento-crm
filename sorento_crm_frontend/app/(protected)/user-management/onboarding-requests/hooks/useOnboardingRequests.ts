'use client';

/**
 * The onboarding queue's hooks layer.
 *
 * Layering: UI -> these hooks -> `services/onboardingService` -> `lib/api-client`.
 * The review screen drives eight writes, and the ones that change a verdict, a
 * status or the link all have the same two jobs after they land: invalidate the
 * request AND the queue, then say what happened. Keeping them here is what stops
 * the component growing a second copy of that rule per button. The cell-level
 * person patch is the exception and says why on itself.
 */

import { useMutation, useQuery, useQueryClient, type QueryKey } from '@tanstack/react-query';
import { toast } from 'sonner';
import { buildDataGridParams } from '@/lib/api-client';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import {
  useRecordNeighbours,
  type RecordNeighboursResult,
} from '@/hooks/useRecordNeighbours';
import {
  applyPersonPatch,
  type OnboardingPersonPatch,
  type OnboardingRequestDetail,
} from '@/components/common/onboarding/types';
import {
  ONBOARDING_NEIGHBOURS_PATH,
  approveOnboardingPerson,
  approveOnboardingRequest,
  createOnboardingRequest,
  deleteOnboardingRequest,
  getOnboardingRequest,
  listOnboardingRequests,
  regenerateOnboardingToken,
  rejectOnboardingPerson,
  revokeOnboardingRequest,
  sendOnboardingRequest,
  startOnboardingReview,
  updateOnboardingPerson,
  type CreateOnboardingRequestInput,
  type OnboardingRequestListParams,
} from '../services/onboardingService';
import type { ListPagerParams, ListPagerPage } from '@/hooks/useListPager';

export const ONBOARDING_LIST_KEY = 'onboarding-requests';
export const ONBOARDING_DETAIL_KEY = 'onboarding-request';

/**
 * The list's React Query key. The detail page's pager rebuilds the SAME key from
 * the URL, so it reads the page the list already fetched.
 */
export function onboardingListQueryKey(
  params: OnboardingRequestListParams,
): QueryKey {
  return [
    ONBOARDING_LIST_KEY,
    params.pageIndex,
    params.pageSize,
    params.sorting,
    params.searchQuery,
    params.statusKey,
  ];
}

/** The list query a detail URL describes, in the shape the list passes. */
export function onboardingListParamsFromUrl(
  params: ListPagerParams,
): OnboardingRequestListParams {
  return {
    pageIndex: params.pageIndex,
    pageSize: params.pageSize,
    sorting: params.sorting,
    searchQuery: params.searchQuery,
    statusKey: params.filters.status_key,
  };
}

/** The pager's two hooks into the onboarding requests list. */
export const onboardingPagerQuery = {
  listQueryKey: (params: ListPagerParams): QueryKey =>
    onboardingListQueryKey(onboardingListParamsFromUrl(params)),
  fetchPage: (params: ListPagerParams): Promise<ListPagerPage> =>
    listOnboardingRequests(onboardingListParamsFromUrl(params)),
};

export function useOnboardingRequests(params: OnboardingRequestListParams) {
  return useQuery({
    queryKey: onboardingListQueryKey(params),
    queryFn: () => listOnboardingRequests(params),
  });
}

export function useOnboardingRequest(id: string | null) {
  return useQuery({
    queryKey: [ONBOARDING_DETAIL_KEY, id],
    queryFn: () => {
      if (!id) throw new Error('An onboarding request id is required');
      return getOnboardingRequest(id);
    },
    enabled: !!id,
  });
}

/**
 * Prev/next within the list query the reviewer navigated from. Serialized with
 * `buildDataGridParams`, the same way the list page sends it, so the backend
 * walks the identical filtered+sorted set.
 */
export function useOnboardingRequestNeighbours(
  requestId: string | null,
  listParams: DataGridApiFetchParams & { statusKey?: string },
): RecordNeighboursResult {
  const params = buildDataGridParams(listParams, { status_key: listParams.statusKey });
  return useRecordNeighbours(ONBOARDING_NEIGHBOURS_PATH, requestId, params);
}

export function useCreateOnboardingRequest() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateOnboardingRequestInput) => createOnboardingRequest(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [ONBOARDING_LIST_KEY] });
      toast.success('Onboarding request created');
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

/**
 * Every write the review screen can make, against one request.
 *
 * They share one `invalidate`, because each of them changes both the row on the
 * detail page and the counts the queue shows for it.
 */
export function useOnboardingRequestMutations(requestId: string) {
  const queryClient = useQueryClient();

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: [ONBOARDING_DETAIL_KEY, requestId] });
    queryClient.invalidateQueries({ queryKey: [ONBOARDING_LIST_KEY] });
    // The pager is cached for 30s, so a verdict that moves this request out of
    // the filtered set would otherwise leave prev/next walking the old one.
    queryClient.invalidateQueries({ queryKey: ['record-neighbours'] });
  };

  const fail = (error: Error) => toast.error(error.message);

  const detailKey = [ONBOARDING_DETAIL_KEY, requestId];

  const patchPerson = useMutation({
    mutationFn: ({ personId, patch }: { personId: string; patch: OnboardingPersonPatch }) =>
      updateOnboardingPerson(requestId, personId, patch),
    // The edit lands on the cached row straight away, and not only once the
    // save has answered.
    //
    // Without this the grid kept showing the row as it was BEFORE the click for
    // as long as the round trip took, and the next click was computed against
    // that stale row. On the needs multi-select that is the difference between a
    // multi-select and a single one: ticking a second need read the first as
    // still unticked and sent it back as false. The same window let a second
    // edit to any other cell overwrite the first.
    onMutate: async ({ personId, patch }) => {
      await queryClient.cancelQueries({ queryKey: detailKey });
      const previous = queryClient.getQueryData<OnboardingRequestDetail>(detailKey);
      if (previous) {
        queryClient.setQueryData<OnboardingRequestDetail>(detailKey, {
          ...previous,
          people: previous.people.map((person) =>
            person.id === personId ? applyPersonPatch(person, patch) : person,
          ),
        });
      }
      return { previous };
    },
    // Deliberately no cache work on success.
    //
    // A refetch here raced the reviewer. Ticking a second need starts save B and
    // then save C; B answers first, its refetch is already on the wire when C is
    // still in flight, and it comes back with the row as it was BEFORE C. That
    // response overwrites the cache, C's optimistic tick vanishes from the grid,
    // and a third click is then computed against a row that lost it - the same
    // "a multi-select behaves like a single one" failure the optimistic apply
    // above was added to fix.
    //
    // Nothing needs the refetch. The optimistic row already carries what was
    // saved, the server changes no other field on this write (it only writes the
    // editable person fields), and the queue summary counts a person patch does
    // not move, so the list and the pager are not stale either. Collision chips
    // stay computed live on read (UAC AC-6.4) - every load, every pager step and
    // every verdict still refetches them.
    onError: (error: Error, _variables, context) => {
      toast.error(error.message);
      // Put the row back the way it was before the optimistic edit, so a refused
      // change does not sit on screen looking saved even for the moment before
      // the refetch answers.
      if (context?.previous) queryClient.setQueryData(detailKey, context.previous);
      // A refused edit must not stay on screen looking saved. The grid buffers
      // by cell and only tells the parent on blur, so it now believes the new
      // value IS the committed one and a second blur is a no-op - the row would
      // read as edited until a reload. Refetching puts the server's value back
      // under the toast, and only into cells nobody is typing into. Concretely:
      // one tab approves the batch, another still shows it in review, an edit
      // there comes back 409, and without this the wrong value simply sits
      // there.
      queryClient.invalidateQueries({ queryKey: [ONBOARDING_DETAIL_KEY, requestId] });
    },
  });

  const approvePerson = useMutation({
    mutationFn: (personId: string) => approveOnboardingPerson(requestId, personId),
    onSuccess: () => {
      invalidate();
      toast.success('Person approved');
    },
    onError: fail,
  });

  const rejectPerson = useMutation({
    mutationFn: ({ personId, reason }: { personId: string; reason: string }) =>
      rejectOnboardingPerson(requestId, personId, reason),
    onSuccess: () => {
      invalidate();
      toast.success('Person rejected');
    },
    onError: fail,
  });

  const startReview = useMutation({
    mutationFn: () => startOnboardingReview(requestId),
    onSuccess: () => {
      invalidate();
      toast.success('Review started');
    },
    onError: fail,
  });

  const approveRequest = useMutation({
    mutationFn: () => approveOnboardingRequest(requestId),
    onSuccess: (result) => {
      invalidate();
      if (result.job_id) {
        toast.success(
          `Approved. Provisioning queued for ${result.queued_people} ${
            result.queued_people === 1 ? 'person' : 'people'
          }.`,
        );
      } else {
        // The approval committed but the queue did not take the job. Saying so
        // is the point: the request sits in Provisioning with nothing running,
        // and silence here would read as "it is working on it".
        toast.warning('Approved, but provisioning could not be queued.');
      }
    },
    onError: fail,
  });

  const send = useMutation({
    mutationFn: () => sendOnboardingRequest(requestId),
    onSuccess: () => {
      invalidate();
      toast.success('Intake link is live');
    },
    onError: fail,
  });

  const revoke = useMutation({
    mutationFn: () => revokeOnboardingRequest(requestId),
    onSuccess: () => {
      invalidate();
      toast.success('Link revoked');
    },
    onError: fail,
  });

  const regenerate = useMutation({
    mutationFn: () => regenerateOnboardingToken(requestId),
    onSuccess: () => {
      invalidate();
      toast.success('New link issued');
    },
    onError: fail,
  });

  const remove = useMutation({
    mutationFn: () => deleteOnboardingRequest(requestId),
    onError: fail,
  });

  return {
    patchPerson,
    approvePerson,
    rejectPerson,
    startReview,
    approveRequest,
    send,
    revoke,
    regenerate,
    remove,
  };
}
