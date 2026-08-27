/**
 * The link horizon, in one place (`PLAN-scm-oi-handshake.md` section 11).
 *
 * Every path that ties a document to an order-inquiry row reaches only as far as a date:
 * a row due after it is left Not linked, so a 2030 order stops eating a purchase order a
 * nearer one needed. Three presses share the date - Acknowledge, Link selected and Link
 * now - plus the manual Link dialog, which shows it and lets a person overrule it.
 *
 * The words a result is reported in live here too, so the three presses cannot come to
 * report the same outcome differently.
 */
import { formatDateInMalaysia } from '@/lib/helpers';
import type { AcknowledgeResult, AutoPlaceResult } from '../types/orderInquiry.types';

/** Where the buyer's own choice is remembered between visits (AC-LH5). */
export const LINK_HORIZON_STORAGE_KEY = 'sorento.order-inquiries.link-up-to';

/** `2026-12-31`, and nothing else. A stored or shared value in any other shape is
 *  ignored rather than half-parsed into a date nobody chose. */
const YMD = /^\d{4}-\d{2}-\d{2}$/;

export function isHorizonDate(value: string | null | undefined): value is string {
  return typeof value === 'string' && YMD.test(value);
}

/** What the buyer chose last time, on this browser. Absent on the server and in a
 *  browser that refuses storage, which reads the same as never having chosen. */
export function readStoredLinkHorizon(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    const stored = window.localStorage.getItem(LINK_HORIZON_STORAGE_KEY);
    return isHorizonDate(stored) ? stored : null;
  } catch {
    return null;
  }
}

/** Remembered per browser. An empty value clears it: the buyer took the horizon off. */
export function storeLinkHorizon(value: string): void {
  if (typeof window === 'undefined') return;
  try {
    if (isHorizonDate(value)) window.localStorage.setItem(LINK_HORIZON_STORAGE_KEY, value);
    else window.localStorage.removeItem(LINK_HORIZON_STORAGE_KEY);
  } catch {
    /* a browser refusing storage is not a reason to refuse the press */
  }
}

/**
 * Where the page's date starts, in the order the answers are trusted (AC-LH5): the URL
 * first, because a shared link is the buyer telling somebody else which horizon to look
 * at; then this browser's own memory; then the reorder plan's coverage date off the
 * summary. Blank when none of the three has one, which means no horizon is in force.
 */
export function initialLinkHorizon(
  fromUrl: string | null | undefined,
  stored: string | null | undefined,
  planDefault: string | null | undefined,
): string {
  if (isHorizonDate(fromUrl)) return fromUrl;
  if (isHorizonDate(stored)) return stored;
  if (isHorizonDate(planDefault)) return planDefault;
  return '';
}

/**
 * Is this row due beyond the horizon?
 *
 * A row with NO delivery date is INSIDE it (AC-LH4): the quantity is still owed, nobody
 * has said when, and holding it back for a date that was never stated would leave it
 * unbought. Both halves are plain `YYYY-MM-DD`, which compares as text.
 */
export function isDueAfterHorizon(
  deliveryDate: string | null | undefined,
  linkUpTo: string | null | undefined,
): boolean {
  if (!isHorizonDate(linkUpTo)) return false;
  const due = (deliveryDate ?? '').slice(0, 10);
  if (!YMD.test(due)) return false;
  return due > linkUpTo;
}

/** `31/12/2026`. The buyer reads dates in their own format everywhere else on this page. */
export function formatHorizon(value: string | null | undefined): string {
  return isHorizonDate(value) ? formatDateInMalaysia(`${value}T00:00:00`) : '';
}

function afterPhrase(after: number, linkUpTo: string | null | undefined): string {
  const when = formatHorizon(linkUpTo);
  return when ? `${after} after ${when}` : `${after} left for later`;
}

/**
 * What a linking press did, in the two figures the banner reports (AC-LH2): "1 linked, 1
 * after 31/12/2026". With nothing held back it keeps saying what it always said - how
 * many rows, across how many document lines - because that is the fact worth having when
 * the horizon changed nothing.
 */
export function linkOutcomeText(result: AutoPlaceResult): string {
  const placed = result.placed_rows ?? 0;
  const after = result.after_horizon ?? 0;
  if (after > 0) {
    return `${placed} linked, ${afterPhrase(after, result.link_up_to)}`;
  }
  if (placed === 0) return 'Nothing new to link yet';
  return (
    `${placed} row${placed === 1 ? '' : 's'} linked across ` +
    `${result.allocations} document line${result.allocations === 1 ? '' : 's'}`
  );
}

/** The same, for the Acknowledge press, which reports what it took on first. */
export function acknowledgeOutcomeText(result: AcknowledgeResult): string {
  const rows = `${result.acknowledged} row${result.acknowledged === 1 ? '' : 's'} acknowledged`;
  const after = result.after_horizon ?? 0;
  if (after > 0) {
    return `${rows}, ${result.linked_rows} linked, ${afterPhrase(after, result.link_up_to)}`;
  }
  if (result.linked_rows === 0) return rows;
  return (
    `${rows}, ${result.linked_rows} linked across ` +
    `${result.links} document line${result.links === 1 ? '' : 's'}`
  );
}
