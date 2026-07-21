import { formatDateTimeInMalaysia } from '@/lib/helpers';
import type { ChatHistoryGroupBy, ChatMessageRow } from './types/chatHistory.types';

/**
 * Malaysia calendar date, matching how every timestamp on this page renders.
 *
 * Deriving it in Malaysia time is not cosmetic: `sent_at` is stored naive UTC,
 * and a message at 08:29 MYT is 00:29 UTC the *previous* day. Grouping on the
 * UTC date would put the same conversation under two different headings.
 */
export function malaysiaDateLabel(iso: string): string {
  return formatDateTimeInMalaysia(iso).split(',')[0].trim();
}

/**
 * Build the "does this row open a new group?" rule, or `undefined` when
 * grouping is off (the grid then renders exactly as before).
 *
 * Only decides where to draw a divider. Making group members *contiguous* is the
 * API's job — see `group_by` in `chat_history_query`. Grouping a paginated set
 * purely client-side would render the same group once per page.
 */
export function buildGroupHeader(
  groupBy: ChatHistoryGroupBy,
): ((row: ChatMessageRow, prev: ChatMessageRow | null) => string | null) | undefined {
  if (groupBy === 'none') return undefined;

  return (row, prev) => {
    const date = malaysiaDateLabel(row.sent_at);
    const prevDate = prev ? malaysiaDateLabel(prev.sent_at) : null;

    if (groupBy === 'date') {
      return date !== prevDate ? date : null;
    }
    if (groupBy === 'contact') {
      return row.contact_display !== prev?.contact_display ? row.contact_display : null;
    }

    // contact_date: contact is the outer group and date the inner one, so a new
    // contact always opens a new date section too — otherwise the first day of
    // each conversation would be unlabelled.
    if (row.contact_display !== prev?.contact_display) {
      return `${row.contact_display} · ${date}`;
    }
    return date !== prevDate ? date : null;
  };
}
