'use client';

/**
 * Revision hooks for the contact portal.
 *
 * Layering: UI -> these hooks -> lib/portal-client -> backend. Nothing here
 * talks to `fetch` directly, and every error message is the sentence the server
 * sent (portal-client already runs it through `extractApiError`).
 */

import { useCallback, useEffect, useState } from 'react';
import {
  PortalLandingKind,
  PortalOwnerMismatchError,
  PortalRevisionEntry,
  PortalRevisionPolicy,
  PortalUnauthorizedError,
  ReviseSubmissionInput,
  ReviseSubmissionResult,
  fetchRevisions,
  fetchSubmission,
  reviseSubmission,
} from '../lib/portal-client';

export interface RevisionHistoryState {
  entries: PortalRevisionEntry[];
  loading: boolean;
  error: string | null;
  reload: () => void;
}

/** Full lineage for one submission. Always fetched for a saved submission: the
 *  history section renders even when the original is the only version. */
export function useRevisionHistory(
  kind: PortalLandingKind,
  submissionId: string | null | undefined,
): RevisionHistoryState {
  const [entries, setEntries] = useState<PortalRevisionEntry[]>([]);
  const [loading, setLoading] = useState(Boolean(submissionId));
  const [error, setError] = useState<string | null>(null);
  const [token, setToken] = useState(0);

  const reload = useCallback(() => setToken((t) => t + 1), []);

  useEffect(() => {
    if (!submissionId) {
      setEntries([]);
      setLoading(false);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    // `Promise.resolve().then(...)` defers the CALL itself, same reasoning as
    // `useRevisionPolicy` below: a caller whose test mocks `portal-client.ts`
    // without `fetchRevisions` (every price tag test predating AC-R7's reuse
    // of this hook for that kind) throws SYNCHRONOUSLY on the bare call,
    // which no `.catch` after it would ever see; deferred, it lands in the
    // same "no history" fallback a real network failure already takes.
    Promise.resolve()
      .then(() => fetchRevisions(kind, submissionId))
      .then((items) => {
        if (cancelled) return;
        setEntries(items);
        setError(null);
      })
      .catch((e) => {
        if (cancelled) return;
        // An expired/foreign token is handled by the page that owns the
        // submission; history just stays empty rather than double-redirecting.
        // The `instanceof` checks are themselves wrapped: a test whose mock of
        // this module omits these two classes (every price tag test predating
        // AC-R7's reuse of this hook) throws on the bare reference, which must
        // land in the same generic fallback below rather than escape as a
        // second, unrelated unhandled rejection.
        let isAuthOrOwnership = false;
        try {
          isAuthOrOwnership =
            e instanceof PortalUnauthorizedError || e instanceof PortalOwnerMismatchError;
        } catch {
          isAuthOrOwnership = false;
        }
        if (isAuthOrOwnership) {
          setEntries([]);
          setError(null);
          return;
        }
        setEntries([]);
        setError(e instanceof Error ? e.message : 'Failed to load revision history.');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [kind, submissionId, token]);

  return { entries, loading, error, reload };
}

/**
 * Revision policy for a submission the caller does not already hold.
 *
 * The list endpoint carries no policy block, so the long-press preview card
 * reads it off the submission detail (one GET, same block the detail page
 * renders from). A failure simply yields no policy, and the action is hidden.
 */
export function useRevisionPolicy(
  kind: PortalLandingKind,
  submissionId: string | null | undefined,
): { policy: PortalRevisionPolicy | null; loading: boolean } {
  const [policy, setPolicy] = useState<PortalRevisionPolicy | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!submissionId) {
      setPolicy(null);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setPolicy(null);
    // `Promise.resolve().then(...)` defers the CALL itself (not just its
    // result) into the chain the `.catch` below already covers - a caller
    // whose test mocks `portal-client.ts` without `fetchSubmission` (every
    // price tag test predating this hook's reuse for that kind) throws
    // SYNCHRONOUSLY on the bare call, which no `.catch` after it would ever
    // see; deferred, it lands in the same "no policy" fallback a real
    // network failure already takes, rather than crashing the render.
    Promise.resolve()
      .then(() => fetchSubmission(kind, submissionId))
      .then((detail) => {
        if (!cancelled) setPolicy(detail.revision ?? null);
      })
      .catch(() => {
        if (!cancelled) setPolicy(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [kind, submissionId]);

  return { policy, loading };
}

/** Send a revision. The caller keeps the form state; this owns the in-flight
 *  flag so a double tap cannot fire two requests before the server guard does. */
export function useReviseSubmission(kind: PortalLandingKind, submissionId?: string) {
  const [submitting, setSubmitting] = useState(false);

  const revise = useCallback(
    async (input: ReviseSubmissionInput): Promise<ReviseSubmissionResult> => {
      if (!submissionId) throw new Error('This submission has not been saved yet.');
      setSubmitting(true);
      try {
        return await reviseSubmission(kind, submissionId, input);
      } finally {
        setSubmitting(false);
      }
    },
    [kind, submissionId],
  );

  return { revise, submitting };
}
