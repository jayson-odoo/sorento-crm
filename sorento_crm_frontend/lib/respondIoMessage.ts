/**
 * Respond.io GET .../message/list: incoming messages often have `status: []`, while outgoing
 * have pending/sent/delivered. Sorting/display must not use only `status[0].timestamp ?? 0`
 * or incoming collapse to epoch and appear at the wrong end of the list.
 */

import { respondIoTimestampToDate } from '@/lib/helpers';

/** Minimal shape for list + panel components */
export type RespondMessageLike = {
  messageId?: number;
  status?: Array<{ value?: string; timestamp?: number; message?: string }>;
};

/**
 * `messageId` from Respond.io is often a Unix microsecond value (~1.7e15), while `status[].timestamp`
 * is Unix milliseconds (~1.7e12). Using the same ms rule for both yields absurd dates and wrong sort.
 */
function respondIoMessageIdToMilliseconds(messageId: number): number {
  if (!Number.isFinite(messageId)) return NaN;
  if (messageId > 1e14) {
    return Math.floor(messageId / 1000);
  }
  return respondIoTimestampToDate(messageId).getTime();
}

/**
 * Latest meaningful instant from status entries (max timestamp), or null if none.
 */
function latestStatusTimeMs(item: RespondMessageLike): number | null {
  const arr = item.status;
  if (!arr?.length) return null;
  let best = -Infinity;
  for (const s of arr) {
    if (s.timestamp == null || s.timestamp <= 0) continue;
    const t = respondIoTimestampToDate(s.timestamp).getTime();
    if (!Number.isNaN(t) && t > best) best = t;
  }
  return best > -Infinity ? best : null;
}

/**
 * Monotonic sort key: status times when present, else `messageId` (µs or ms depending on magnitude).
 */
export function getRespondMessageSortTimeMs(item: RespondMessageLike): number {
  const fromStatus = latestStatusTimeMs(item);
  if (fromStatus != null) return fromStatus;
  const mid = item.messageId;
  if (typeof mid === 'number' && Number.isFinite(mid)) {
    const ms = respondIoMessageIdToMilliseconds(mid);
    return Number.isFinite(ms) ? ms : 0;
  }
  return 0;
}

/**
 * Display time: prefer latest status entry; if incoming with empty status, fall back to messageId.
 */
export function getRespondMessageDisplayTimeMs(item: RespondMessageLike): number {
  const fromStatus = latestStatusTimeMs(item);
  if (fromStatus != null) return fromStatus;
  const mid = item.messageId;
  if (typeof mid === 'number' && Number.isFinite(mid)) {
    const ms = respondIoMessageIdToMilliseconds(mid);
    return Number.isFinite(ms) ? ms : 0;
  }
  return 0;
}
