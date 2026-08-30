'use client';

import { useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { toast } from 'sonner';
import { pendingEntityStore } from '@/lib/pending-entity-store';

/**
 * What a link to a record this tab just deleted should do (S6 feedback C).
 *
 * A deferred delete leaves the row on screen for its window, and the list the
 * user came back to may still be serving it out of the React Query cache for a
 * moment after. Clicking it lands on a detail page whose every read 404s, and
 * today that reads as a fault: a red toast, then "Product not found" on an empty
 * page, for something the user themselves asked for.
 *
 * So: only for an id this tab WATCHED a delete commit on, say "Already deleted"
 * once and go back to the list. A genuinely wrong URL keeps the not-found page,
 * because that one really is a surprise and the reader has to see it.
 */
export interface UseDeletedRecordGuardInput {
  entityId: string | null | undefined;
  /** The record's read has settled and there is nothing to show. */
  notFound: boolean;
  /** Where the record lived, search string and all. */
  listPath: string;
}

/** True once the guard has taken over, so the caller renders nothing. */
export function useDeletedRecordGuard({
  entityId,
  notFound,
  listPath,
}: UseDeletedRecordGuardInput): boolean {
  const router = useRouter();
  const handledRef = useRef(false);
  const gone = !!entityId && notFound && pendingEntityStore.wasDeletedId(entityId);

  useEffect(() => {
    if (!gone || handledRef.current) return;
    handledRef.current = true;
    // Quiet, and keyed, so a tab's worth of dead reads cannot stack it up.
    toast('Already deleted', { id: `already-deleted-${entityId}` });
    router.replace(listPath);
  }, [gone, entityId, listPath, router]);

  return gone;
}

export default useDeletedRecordGuard;
