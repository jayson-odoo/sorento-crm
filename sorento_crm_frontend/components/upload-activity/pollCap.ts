/**
 * When the header bell keeps polling the upload-activity feed (INTEGRATION-LOG-INDEXES).
 *
 * An upload whose integration_log row is stuck `sent` / `pending` reads `processing` forever,
 * so "poll every 5 s while anything is processing" never stopped, and each poll ran a heavy
 * query. An attachment session counts as in flight for POLLING only while it started less than
 * `POLL_CAP_MINUTES` ago: n8n intake replies in seconds to a few minutes, so an older one is
 * stuck. Its displayed status is unchanged, and opening the drawer still refetches, so a late
 * reply still shows.
 *
 * Not capped: `import_job` sessions (an RQ job reports its own progress, and a large import can
 * legitimately run past 30 minutes), and optimistic sessions still uploading in this tab.
 */

import { parseServerDate } from './timeUtil';
import type { UploadActivitySession } from './types';

export const POLL_CAP_MINUTES = 30;
export const POLL_INTERVAL_MS = 5_000;

export function shouldPollBackend(
  sessions: UploadActivitySession[],
  now: number = Date.now(),
): boolean {
  const cutoff = now - POLL_CAP_MINUTES * 60_000;
  return sessions.some(
    (s) =>
      (s.status === 'uploading' || s.status === 'processing') &&
      (s.session_type === 'import_job' ||
        parseServerDate(s.started_at).getTime() >= cutoff),
  );
}

/** The bell query's `refetchInterval`: poll while an optimistic upload or a capped backend
 * session is in flight, otherwise stop. */
export function pollIntervalFor(
  latest: UploadActivitySession[] | undefined,
  optimisticInFlight: boolean,
  now: number = Date.now(),
): number | false {
  if (optimisticInFlight) return POLL_INTERVAL_MS;
  return latest && shouldPollBackend(latest, now) ? POLL_INTERVAL_MS : false;
}
