/**
 * When the header bell keeps polling the upload-activity feed (INTEGRATION-LOG-INDEXES).
 *
 * An upload whose integration_log row is stuck `sent` / `pending` reads `processing` forever,
 * so "poll every 5 s while anything is processing" never stopped, and each poll ran a heavy
 * query. A backend session counts as in flight for POLLING only while it started less than
 * `POLL_CAP_MINUTES` ago: n8n intake replies in seconds to a few minutes, so an older one is
 * stuck. Its displayed status is unchanged, and opening the drawer still refetches, so a late
 * reply still shows. Optimistic sessions (still uploading in this tab) are not capped; the
 * caller decides those.
 */

import { parseServerDate } from './timeUtil';
import type { UploadActivitySession } from './types';

export const POLL_CAP_MINUTES = 30;

export function shouldPollBackend(
  sessions: UploadActivitySession[],
  now: number = Date.now(),
): boolean {
  const cutoff = now - POLL_CAP_MINUTES * 60_000;
  return sessions.some(
    (s) =>
      (s.status === 'uploading' || s.status === 'processing') &&
      parseServerDate(s.started_at).getTime() >= cutoff,
  );
}
