import type { RespondMessageItem } from '@/app/(protected)/procurement-management/stock-inquiries/services/stockInquiryService';

/**
 * Normalise Respond.io time: API may use seconds or ms.
 */
function rawToMs(raw: number): number {
  if (!Number.isFinite(raw)) return NaN;
  return raw > 1e12 ? raw : raw * 1000;
}

/** Ignore placeholder / corrupt API times (e.g. SLA “1970-01-01”) when sorting. */
const MIN_VALID_MESSAGE_MS = Date.UTC(1990, 0, 1);

function isValidSortMs(t: number): boolean {
  return Number.isFinite(t) && t >= MIN_VALID_MESSAGE_MS;
}

function getDeliveredStatusTimeMs(item: RespondMessageItem): number {
  for (const s of item.status ?? []) {
    if (s?.value !== 'delivered') continue;
    if (s.timestamp == null || !Number.isFinite(s.timestamp)) continue;
    const t = rawToMs(s.timestamp);
    if (isValidSortMs(t)) return t;
  }
  return 0;
}

/**
 * Best-effort “when this message belongs in the thread” for ordering.
 *
 * Using `Math.min` across root + every status event was wrong: bogus early status times
 * (SLA placeholders), stale template `createdAt`, etc. pulled messages far from their real
 * position. Inbox order aligns better with the **latest** valid status timestamp (sent /
 * delivered / read chain), then root fields if there are no statuses.
 */
export function getRespondMessageSortTimeMs(item: RespondMessageItem): number {
  const r = item as Record<string, unknown>;
  const fromRoot: number[] = [];
  for (const k of ['timestamp', 'createdAt', 'created_at', 'messageTime', 'message_time'] as const) {
    const v = r[k];
    if (typeof v === 'number' && Number.isFinite(v)) {
      const t = rawToMs(v);
      if (isValidSortMs(t)) fromRoot.push(t);
    }
  }
  const statusTimes: number[] = [];
  for (const s of item.status ?? []) {
    if (s?.timestamp != null && Number.isFinite(s.timestamp)) {
      const t = rawToMs(s.timestamp);
      if (isValidSortMs(t)) statusTimes.push(t);
    }
  }
  if (statusTimes.length > 0) {
    return Math.max(...statusTimes);
  }
  if (fromRoot.length > 0) {
    return Math.max(...fromRoot);
  }
  if (item.messageId != null && Number.isFinite(item.messageId)) {
    return item.messageId;
  }
  return 0;
}

export function compareRespondMessages(a: RespondMessageItem, b: RespondMessageItem): number {
  // Respond message IDs are monotonic and best represent server conversation order.
  const ma = a.messageId;
  const mb = b.messageId;
  const aHasId = typeof ma === 'number' && Number.isFinite(ma);
  const bHasId = typeof mb === 'number' && Number.isFinite(mb);
  if (aHasId && bHasId && ma !== mb) return ma - mb;
  if (aHasId !== bHasId) return aHasId ? -1 : 1;

  const ta = getRespondMessageSortTimeMs(a);
  const tb = getRespondMessageSortTimeMs(b);
  if (ta !== tb) return ta - tb;
  if (aHasId && bHasId && ma !== mb) return ma - mb;
  return 0;
}

export function getRespondMessageDisplayTimeMs(item: RespondMessageItem): number {
  const delivered = getDeliveredStatusTimeMs(item);
  if (delivered > 0) return delivered;

  const statusTimes: number[] = [];
  for (const s of item.status ?? []) {
    if (s?.timestamp != null && Number.isFinite(s.timestamp)) {
      const t = rawToMs(s.timestamp);
      if (isValidSortMs(t)) statusTimes.push(t);
    }
  }
  if (statusTimes.length > 0) return Math.max(...statusTimes);

  const r = item as Record<string, unknown>;
  const fromRoot: number[] = [];
  for (const k of ['timestamp', 'createdAt', 'created_at', 'messageTime', 'message_time'] as const) {
    const v = r[k];
    if (typeof v === 'number' && Number.isFinite(v)) {
      const t = rawToMs(v);
      if (isValidSortMs(t)) fromRoot.push(t);
    }
  }
  if (fromRoot.length > 0) return Math.max(...fromRoot);
  return 0;
}
