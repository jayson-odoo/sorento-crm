'use client';

import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';

import {
  adoptCode,
  applyDimensions,
  createFlyerReadingFromAttachment,
  getFlyerReading,
  listFlyerReadings,
  seedFromFlyerReading,
  uploadFlyerReading,
  type DimensionApplyInput,
  type DimensionApplyResult,
  type FlyerReading,
  type FlyerReadingSummary,
  type FlyerSeedInput,
  type FlyerSeedResult,
} from '../../services/flyerReadingService';

export const FLYER_READINGS_QUERY_KEY = 'dealer-kit-flyer-readings';

/** How often a reading that is still being read is asked about again. */
const PROCESSING_POLL_MS = 3000;

/**
 * The flyers read so far, and the ones being read right now.
 *
 * Polls only while something is `processing`, and stops the moment nothing is:
 * a read takes tens of seconds, so a designer who is watching gets the flip to
 * Done without touching anything, and a designer who is not costs the server
 * nothing.
 */
export function useFlyerReadingsQuery() {
  return useQuery({
    queryKey: [FLYER_READINGS_QUERY_KEY],
    queryFn: listFlyerReadings,
    refetchInterval: (query) =>
      (query.state.data ?? []).some((row) => row.status === 'processing')
        ? PROCESSING_POLL_MS
        : false,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

/**
 * One reading and the report as it stands RIGHT NOW.
 *
 * `promotionId` is part of the key because the report is recomputed per
 * promotion: caching one answer under a promotion-blind key would show
 * "printed but not in this promotion" figures for a promotion nobody picked.
 *
 * `staleTime: 0` because the report is derived from the product master, which
 * moves. A reviewer who creates the missing product in another tab and comes
 * back must see the list shrink, not a cached copy telling them to do it again.
 */
export function useFlyerReadingQuery(readingId: string, promotionId: string | null) {
  return useQuery({
    queryKey: [FLYER_READINGS_QUERY_KEY, readingId, promotionId ?? ''],
    queryFn: () => getFlyerReading(readingId, promotionId),
    enabled: Boolean(readingId),
    // Changing the promotion is a new key and therefore a new query. Without
    // this the whole review - every section a reviewer was reading, and the
    // half-filled seed form under it - is replaced by a skeleton for the length
    // of a match run. The previous answer stays on screen and the header says
    // it is being recomputed.
    placeholderData: (previous) => previous,
    // Same rule as the list: a reading opened while its job is still running
    // fills itself in. Somebody who clicked a Processing row is the person most
    // likely to be waiting for it.
    refetchInterval: (query) =>
      query.state.data?.status === 'processing' ? PROCESSING_POLL_MS : false,
    staleTime: 0,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

/**
 * What happens after a flyer has been HANDED OVER, whichever source it came
 * from.
 *
 * Shared by both create hooks on purpose: the two sources produce the same
 * reading, so anything one of them did to the cache and not the other would be
 * a difference the designer could see.
 *
 * The list is invalidated and nothing else. There is no report yet to seed a
 * detail cache with, and no reason to send anybody to a screen that has nothing
 * on it - the row appears at the top of the list as Processing, which is where
 * the toast says to look.
 *
 * A 202 does NOT mean the read is on its way. The backend answers 202 with a
 * row already `failed` when it could not queue the job at all (Redis down), and
 * telling that designer their flyer is being read in the background is telling
 * them something that will never happen. The row is right here, so it decides
 * which toast they get.
 */
function onFlyerReadingCreated(queryClient: QueryClient, reading: FlyerReadingSummary) {
  queryClient.invalidateQueries({ queryKey: [FLYER_READINGS_QUERY_KEY] });
  if (reading.status === 'failed') {
    toast.error(reading.errorMessage || 'Could not read that flyer');
    return;
  }
  toast.success('Reading the flyer in the background - it will appear in your uploads');
}

function onFlyerReadingFailed(error: Error) {
  // The backend says "not a PDF" and "larger than the 50 MB limit" in words,
  // so the message is passed through rather than replaced.
  toast.error(error.message || 'Could not read that flyer');
}

/**
 * Read a flyer off the designer's machine. Queued on the server, so this
 * resolves as soon as the row exists - with the row, not the report.
 */
export function useUploadFlyerReading() {
  const queryClient = useQueryClient();

  return useMutation<FlyerReadingSummary, Error, { file: File; promotionId?: string | null }>({
    mutationFn: ({ file, promotionId }) => uploadFlyerReading(file, promotionId),
    onSuccess: (reading) => onFlyerReadingCreated(queryClient, reading),
    onError: onFlyerReadingFailed,
  });
}

/**
 * Read a flyer the file library already holds. Only the attachment id travels;
 * everything else the server takes off the attachment.
 */
export function useCreateFlyerReadingFromAttachment() {
  const queryClient = useQueryClient();

  return useMutation<
    FlyerReadingSummary,
    Error,
    { attachmentId: string; promotionId?: string | null }
  >({
    mutationFn: ({ attachmentId, promotionId }) =>
      createFlyerReadingFromAttachment(attachmentId, promotionId),
    onSuccess: (reading) => onFlyerReadingCreated(queryClient, reading),
    onError: onFlyerReadingFailed,
  });
}

/**
 * Write printed sizes onto the product master.
 *
 * The READING is invalidated afterwards, unlike the seed, and that is the whole
 * point: the report is derived from the master, so an applied row must come
 * back as an agreement rather than sitting there as a candidate somebody
 * applies again on their next visit. Every promotion's copy of the report is
 * invalidated, not just the one on screen, because they all read the same
 * products.
 *
 * No toast on success. The result is a list of what applied AND what did not,
 * and a green "Done" beside three silent refusals is the failure this endpoint
 * was shaped to prevent. Failures still toast, because a request that never
 * landed has nothing to render.
 */
export function useApplyDimensions(readingId: string) {
  const queryClient = useQueryClient();

  return useMutation<DimensionApplyResult, Error, DimensionApplyInput>({
    mutationFn: (input) => applyDimensions(readingId, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [FLYER_READINGS_QUERY_KEY, readingId] });
    },
    onError: (error) => {
      toast.error(error.message || 'Could not apply these sizes to the product master');
    },
  });
}

/**
 * Build the draft brochure.
 *
 * The pages list is invalidated because a new brochure has just appeared in it.
 * The READING is not: nothing about it changed, and refetching would throw away
 * the report the reviewer is still reading the skipped codes against.
 */
export function useSeedFromFlyerReading(readingId: string) {
  const queryClient = useQueryClient();

  return useMutation<FlyerSeedResult, Error, FlyerSeedInput>({
    mutationFn: (input) => seedFromFlyerReading(readingId, input),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['dealer-kit', 'pages'] });
      toast.success(`Draft v${result.version} created`);
    },
    onError: (error) => {
      toast.error(error.message || 'Could not create the draft brochure');
    },
  });
}

/**
 * Write ONLY the cache entry for the promotion the response was computed
 * against, and invalidate the reading's other promotion-keyed entries so a
 * screen showing a different promotion refetches rather than displaying an
 * answer computed for one it is not looking at.
 *
 * The query is keyed `[FLYER_READINGS_QUERY_KEY, readingId, promotionId ?? '']`
 * (`useFlyerReadingQuery`). `setQueryData` on the exact key writes only the
 * entry the response matches; `invalidateQueries` with a predicate excluding
 * that key marks every other promotion's copy stale without a blind
 * write-through that would show one promotion's report under another's key.
 *
 * Only `useAdoptCode` below calls this. Undo is a detach action (D7) and goes
 * through the deferred pending-action mechanism instead
 * (`flyer_reading.undo_code_adopt`, `useDeferredRowAction` in
 * `MatchReportSections`): the commit runs on the server on its own schedule and
 * answers with a generic outcome, not a `FlyerReading`, so there is nothing to
 * write through - the reading's cache is invalidated (`invalidateKeys`) instead.
 */
function replaceReadingCache(
  queryClient: QueryClient,
  readingId: string,
  promotionId: string | null,
  reading: FlyerReading,
) {
  const exactKey = [FLYER_READINGS_QUERY_KEY, readingId, promotionId ?? ''];
  queryClient.setQueryData<FlyerReading>(exactKey, reading);
  queryClient.invalidateQueries({
    queryKey: [FLYER_READINGS_QUERY_KEY, readingId],
    predicate: (query) => !isSameKey(query.queryKey, exactKey),
  });
}

function isSameKey(a: readonly unknown[], b: readonly unknown[]): boolean {
  return a.length === b.length && a.every((value, index) => value === b[index]);
}

/**
 * "This printed code IS that product" (PLAN-flyer-code-adopt.md). The
 * response is the reading with the code already moved into `matched`, so the
 * row flips in place rather than waiting on a second round trip.
 */
export function useAdoptCode(readingId: string, promotionId: string | null) {
  const queryClient = useQueryClient();

  return useMutation<FlyerReading, Error, { printedCode: string; productId: string }>({
    mutationFn: ({ printedCode, productId }) =>
      adoptCode(readingId, printedCode, productId, promotionId),
    onSuccess: (reading, { printedCode }) => {
      replaceReadingCache(queryClient, readingId, promotionId, reading);
      const adopted = reading.report.matched.find((entry) => entry.code === printedCode);
      toast.success(`${printedCode} adopted as ${adopted?.productCode ?? 'the chosen product'}`);
    },
    onError: (error) => {
      // The 409 naming the code and page this product is already adopted as
      // (R1) is the one message the reviewer needs, so it is passed through.
      toast.error(error.message || 'Could not adopt this code');
    },
  });
}
