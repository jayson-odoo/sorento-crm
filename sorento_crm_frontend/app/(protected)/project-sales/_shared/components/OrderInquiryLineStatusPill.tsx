'use client';

import { statusPillClass } from '@/lib/status-pill';
import { ackOverrideHint, ackStateOf, ackStatusText } from '../lib/orderInquiryAck';
import type { OrderInquiryLine } from '../lib/orderInquiryLineFold';
import { OrderInquiryLineStatePill, ReservePill, STATE_LABEL } from './OrderInquiryVerbPill';
import { OrderInquiryRejectedBadge } from './OrderInquiryRejectedBadge';

/** The status pill keeps the text's own case ("To order · 220 left"), so no capitalize. */
export const ACK_PILL_BASE =
  'inline-flex shrink-0 items-center whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-semibold';

function ackPalette(row: Parameters<typeof ackStateOf>[0]): string {
  const state = ackStateOf(row);
  return state === 'acknowledged' ? 'approved' : state === 'rejected' ? 'voided' : 'pending';
}

/**
 * The ONE status word and colour of a single worklist row, in the line pill's precedence:
 * Waiting for CS, then SO cancelled, then Line cancelled, else today's acknowledgement text.
 * The worklist's Status column prints this, and the server sorts on the same words.
 */
export function rowStatusPill(
  row: Parameters<typeof ackStatusText>[0] & { line_cancelled?: boolean },
): { text: string; palette: string } {
  if (row.waiting_for_cs) return { text: 'Waiting for CS', palette: 'pending' };
  if (row.so_cancelled) return { text: 'SO cancelled', palette: 'voided' };
  if (row.line_cancelled) return { text: 'Line cancelled', palette: 'voided' };
  return { text: ackStatusText(row), palette: ackPalette(row) };
}

/** A waiting change that cancels the line (the SO was cancelled / deleted, or the line removed). */
function waitsOnCancel(row: { waiting_for_cs?: boolean; waiting_change?: { kind?: string } | null }): boolean {
  const kind = row.waiting_change?.kind;
  return Boolean(row.waiting_for_cs) && (kind === 'so_cancelled' || kind === 'line_removed');
}

/** "Waiting for CS · date 18/12/2026 -> 17/01/2027" for a waiting date / qty / product / location
 * change; null for a cancel (which keeps its own pill) or a row that is not waiting. */
export function waitingChangeText(row: {
  waiting_for_cs?: boolean;
  waiting_change?: { kind?: string; was?: string | null; now?: string | null } | null;
}): string | null {
  const change = row.waiting_change;
  if (!row.waiting_for_cs || !change || waitsOnCancel(row)) return null;
  const noun: Record<string, string> = {
    date: 'date',
    qty: 'qty',
    product: 'item',
    location: 'location',
  };
  const label = noun[change.kind ?? ''];
  if (!label) return null;
  return `Waiting for CS \u00b7 ${label} ${change.was ?? '-'} -> ${change.now ?? '-'}`;
}

/**
 * The purchasing worklist's Status cell for one row: the same pills the line pill uses, from the
 * row's own flags. A waiting cancel is the plain Line cancelled pill plus a Waiting for CS marker;
 * a waiting date / qty change names the change.
 */
export function RowStatusCell({
  row,
}: {
  row: Parameters<typeof rowStatusPill>[0] & {
    waiting_change?: { kind?: string; was?: string | null; now?: string | null } | null;
  };
}) {
  if (waitsOnCancel(row)) {
    return (
      <span className="inline-flex flex-wrap items-center gap-1">
        <span className={`${ACK_PILL_BASE} ${statusPillClass('voided')}`} title="Line cancelled">
          Line cancelled
        </span>
        <span className={`${ACK_PILL_BASE} ${statusPillClass('pending')}`} title="Waiting for CS">
          Waiting for CS
        </span>
      </span>
    );
  }
  const changeText = waitingChangeText(row);
  const { text, palette } = changeText
    ? { text: changeText, palette: 'pending' }
    : rowStatusPill(row);
  return (
    <span className={`${ACK_PILL_BASE} ${statusPillClass(palette)}`} title={text}>
      {text}
    </span>
  );
}

const LIVE_LINE_STATES = ['raised', 'partly_linked', 'placed', 'to_confirm'];

function reserveStateOf(line: OrderInquiryLine): string | null | undefined {
  return line.liveRows.length > 0 ? line.primary.reserve_state : null;
}

/** The pill reads a reserve state first, whatever else the line is. */
function showsReservePill(line: OrderInquiryLine): boolean {
  const state = reserveStateOf(line);
  return state === 'requested' || state === 'reserved' || state === 'declined';
}

/**
 * Whether this line's pill is the Rejected badge (with its own lightbox). ONE rule, read by
 * the pill below and by any caller that wraps the pill (the Sales Order's Order inquiry cell
 * opens its documents lightbox only when the pill is not already the Rejected button).
 */
export function lineShowsRejectedBadge(line: OrderInquiryLine): boolean {
  return (
    !showsReservePill(line) &&
    LIVE_LINE_STATES.includes(line.state) &&
    ackStateOf(line.primary) === 'rejected'
  );
}

/**
 * The ONE status word of a folded line: the words the pill below prints, minus its figures
 * ("To order · 8 left" is "To order"; "Request to reserve 4" is "Request to reserve"). The OI
 * Lines tab's State filter offers `LINE_STATUS_OPTIONS` and matches a line when it reads the
 * chosen word, so the filter and the State column cannot disagree.
 */
export function lineStatusWord(line: OrderInquiryLine): string {
  const primary = line.primary;
  if (showsReservePill(line)) {
    const reserve = reserveStateOf(line);
    return reserve === 'requested'
      ? 'Request to reserve'
      : reserve === 'reserved'
        ? 'Reserved'
        : 'Not reserved';
  }
  if (primary.waiting_for_cs) return 'Waiting for CS';
  if (line.state === 'line_cancelled' && primary.so_cancelled) return 'SO cancelled';
  if (!LIVE_LINE_STATES.includes(line.state)) {
    if (line.state === 'line_cancelled') return 'Line cancelled';
    if (line.state === 'nothing_to_buy') return 'Nothing to buy';
    if (line.state === 'to_confirm') return 'To order';
    return STATE_LABEL[line.state] ?? line.state;
  }
  if (lineShowsRejectedBadge(line)) return 'Rejected';
  return ackStatusText(primary).split(' \u00b7 ')[0];
}

/**
 * Every filter value a line answers to: its own word, and "Line cancelled" too when it is a
 * waiting cancelled line (the pill shows both the Line cancelled pill and the waiting marker).
 */
export function lineStatusValues(line: OrderInquiryLine): string[] {
  const own = lineStatusValue(line);
  return waitsOnCancel(line.primary) ? [own, 'Line cancelled'] : [own];
}

/** The reserve words keep the URL values older links carry (`view_state=reserve:requested`). */
const LINE_STATUS_URL_VALUE: Record<string, string> = {
  'Request to reserve': 'reserve:requested',
  Reserved: 'reserve:reserved',
  'Not reserved': 'reserve:declined',
};

/** The filter value of a line: its status word, or the reserve word's URL value. */
export function lineStatusValue(line: OrderInquiryLine): string {
  const word = lineStatusWord(line);
  return LINE_STATUS_URL_VALUE[word] ?? word;
}

/** Every word `lineStatusWord` can give a live, non-historical line, in the order they are offered. */
export const LINE_STATUS_OPTIONS: { value: string; label: string }[] = [
  'To order',
  'Waiting for CS',
  'Done',
  'Rejected',
  'SO cancelled',
  'Line cancelled',
  'Nothing to buy',
  'Request to reserve',
  'Reserved',
  'Not reserved',
].map((word) => ({ value: LINE_STATUS_URL_VALUE[word] ?? word, label: word }));

/**
 * SO-LINE-OI-STATUS-UNIFY (owner, 5 Nov 2026): the ONE status of a sales order line's
 * order inquiry rows, folded by `foldInquiryLines`. The OI Lines tab's State cell and the
 * Sales Order Lines tab's Order inquiry cell both render this, so the two screens can no
 * longer say two different things about the same line.
 *
 * In order: an open reserve (Request to reserve N / Reserved N / Not reserved), a refusal
 * (Rejected + reason, lightbox on click), the purchasing status of a live line (To order,
 * To order · N left, Done; OI-AUTO-CONFIRM), else the line's own state (Line cancelled,
 * Nothing to buy, Cancelled).
 */
export function OrderInquiryLineStatusPill({
  line,
  rejectedTestId,
}: {
  line: OrderInquiryLine;
  rejectedTestId?: string;
}) {
  const primary = line.primary;
  if (showsReservePill(line)) {
    return (
      <ReservePill
        reserveState={reserveStateOf(line)}
        reservedQty={primary.reserved_qty}
        requestedQty={primary.requested_qty}
      />
    );
  }
  // OI-WHOLE-SO-CANCEL v2 (AC-V2-5): a change waiting for CS reads before anything else
  // (a removed line included), then a cancelled SO ahead of "Line cancelled".
  if (waitsOnCancel(primary)) {
    // The EXISTING line-cancelled pill, plus a separate Waiting for CS marker.
    return (
      <span className="inline-flex flex-wrap items-center gap-1">
        <OrderInquiryLineStatePill state="line_cancelled" />
        <OrderInquiryLineStatePill state="waiting_for_cs" />
      </span>
    );
  }
  const changeText = waitingChangeText(primary);
  if (changeText) {
    return (
      <span className={`${ACK_PILL_BASE} ${statusPillClass('pending')}`} title={changeText}>
        {changeText}
      </span>
    );
  }
  if (primary.waiting_for_cs) return <OrderInquiryLineStatePill state="waiting_for_cs" />;
  if (line.state === 'line_cancelled' && primary.so_cancelled) {
    return <OrderInquiryLineStatePill state="so_cancelled" />;
  }
  if (!LIVE_LINE_STATES.includes(line.state)) {
    return <OrderInquiryLineStatePill state={line.state} />;
  }
  if (lineShowsRejectedBadge(line)) {
    return <OrderInquiryRejectedBadge refusal={primary} testId={rejectedTestId} />;
  }
  const text = ackStatusText(primary);
  return (
    <span
      className={`${ACK_PILL_BASE} ${statusPillClass(ackPalette(primary))}`}
      title={[text, ackOverrideHint(primary)].filter(Boolean).join('. ')}
    >
      {text}
    </span>
  );
}
