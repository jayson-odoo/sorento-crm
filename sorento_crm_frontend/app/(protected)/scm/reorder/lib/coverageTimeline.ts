/**
 * Coverage Timeline - PURE display helpers (UAC Group B). No React, no fetching.
 *
 * The one rule this file exists to honour: **months are display grouping only**
 * (AC-B3). Grouping never touches a balance - `groupRowsByMonth` re-partitions the
 * rows the server already accumulated and returns them untouched, so no arithmetic
 * can hide in the presentation layer.
 *
 * Survives Phase 2. Only `coverageMockStore.ts` is deleted.
 */
import type { CoverageRow, CoverageShortfall } from '../types/coverage.types';

/** One month heading plus the rows underneath it. `key` is null for the opening row. */
export interface CoverageMonthGroup {
  /** `YYYY-MM`, or null for the undated opening row. */
  key: string | null;
  /** Rendered heading, e.g. "Jul 2026". */
  label: string;
  rows: CoverageRow[];
}

const MONTH_FMT = new Intl.DateTimeFormat('en-MY', { month: 'short', year: 'numeric' });

const DAY_FMT = new Intl.DateTimeFormat('en-MY', {
  day: '2-digit',
  month: 'short',
  year: 'numeric',
  timeZone: 'UTC',
});

/** `2026-07-01` -> `Jul 2026`. Parsed as a plain date, so no timezone shift. */
export function monthLabel(isoDate: string): string {
  const [y, m] = isoDate.split('-').map(Number);
  if (!y || !m) return isoDate;
  return MONTH_FMT.format(new Date(Date.UTC(y, m - 1, 1)));
}

/**
 * `2026-08-03` -> `03 Aug 2026`.
 *
 * Built on `Date.UTC` and formatted in UTC on purpose. An event date is a plain
 * calendar date with no time and no zone; running it through a local-timezone
 * formatter moves a 1 Jul required-date to 30 Jun west of Greenwich, which would
 * silently reorder the timeline against the balances the server accumulated.
 */
export function dayLabel(isoDate: string | null): string {
  if (!isoDate) return '';
  const [y, m, d] = isoDate.slice(0, 10).split('-').map(Number);
  if (!y || !m || !d) return isoDate;
  return DAY_FMT.format(new Date(Date.UTC(y, m - 1, d)));
}

/**
 * `2026-08-03T09:12:00` -> `03 Aug 2026, 09:12`.
 *
 * Rendered as written, with NO conversion: `computed_at` is already naive Malaysia
 * wall-clock (see `coverage.types.ts`). Passing it to `formatDateTimeInMalaysia`,
 * which reads a naive string as UTC, would add eight hours to a timestamp that is
 * already local.
 */
export function computedAtLabel(iso: string | null): string {
  if (!iso) return '';
  const [datePart, timePart] = iso.split('T');
  const day = dayLabel(datePart);
  const time = (timePart ?? '').slice(0, 5);
  return time ? `${day}, ${time}` : day;
}

/**
 * Partition rows under month headings, preserving order and every balance.
 * Mirrors the backend's `group_by_month` so the two cannot drift.
 */
export function groupRowsByMonth(rows: CoverageRow[]): CoverageMonthGroup[] {
  const out: CoverageMonthGroup[] = [];
  for (const row of rows) {
    const at = row.event.at;
    const key = at ? at.slice(0, 7) : null;
    const last = out[out.length - 1];
    if (last && last.key === key) {
      last.rows.push(row);
      continue;
    }
    out.push({
      key,
      label: key ? monthLabel(`${key}-01`) : 'Opening',
      rows: [row],
    });
  }
  return out;
}

/** Whole days between two ISO dates, ignoring time of day. */
export function daysBetween(fromIso: string, toIso: string): number | null {
  const from = Date.parse(`${fromIso.slice(0, 10)}T00:00:00Z`);
  const to = Date.parse(`${toIso.slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(from) || Number.isNaN(to)) return null;
  return Math.round((to - from) / 86_400_000);
}

/** The supply that arrives too late, and by how many days. */
export interface LateSupply {
  ref: string;
  label: string;
  at: string;
  qty: number;
  days_late: number;
}

/**
 * The first supply event dated AFTER the shortfall (AC-B4).
 *
 * This is what makes the gap legible instead of netted away: a PO of 200 arriving
 * 25 Aug against an order due 3 Aug leaves the closing balance positive while the
 * order is still short, and the number a planner needs is the 22 days between them.
 * Reads the rows the server produced; computes no balance.
 */
export function firstLateSupply(
  rows: CoverageRow[],
  shortfall: CoverageShortfall | null,
): LateSupply | null {
  if (!shortfall?.at) return null;
  for (const row of rows) {
    const e = row.event;
    if (e.kind !== 'supply' || !e.at) continue;
    const gap = daysBetween(shortfall.at, e.at);
    if (gap === null || gap <= 0) continue;
    return { ref: e.ref, label: e.label, at: e.at, qty: e.qty, days_late: gap };
  }
  return null;
}

/**
 * The incoming supply on the timeline, split by stage.
 *
 * Their SUM is what the running balance already used; the SPLIT is what a person
 * deciding a quantity reads, because only the on-order half can still be re-dated
 * or cancelled. Derived from the rows the server produced, so it can never disagree
 * with the balance.
 */
export function supplySplit(rows: CoverageRow[]): { on_order: number; in_transit: number } {
  let onOrder = 0;
  let inTransit = 0;
  for (const row of rows) {
    const e = row.event;
    if (e.kind !== 'supply') continue;
    if (e.supply_stage === 'in_transit') inTransit += e.qty;
    else onOrder += e.qty;
  }
  return { on_order: onOrder, in_transit: inTransit };
}

/** Short human name for a cover source. */
export const SOURCE_LABEL: Record<string, string> = {
  own: 'Own bin',
  brw: 'Shared pool',
  other_project: "Another holder's bin",
  order: 'Purchase',
};

/** Short human name for a supply stage. */
export const SUPPLY_STAGE_LABEL: Record<string, string> = {
  on_order: 'On order',
  in_transit: 'In transit',
};

/**
 * The one-line verdict a planner acts on: use existing stock, or buy.
 * `use_stock` true is the SRTWT7408 case - demand 67 against a pool holding 4,397
 * must read "use the pool", never a buy of 67 (AC-B1c).
 *
 * It answers ONE question: is the committed demand covered from stock we already hold.
 * The reorder engine on the same screen answers a different one: is stock above its
 * reorder point. Those disagree routinely, so when the demand is covered AND the balance
 * is under the floor, the verdict states its own scope and reports the other answer
 * beside it. Left unqualified it read "existing stock covers it" next to a grid row
 * recommending a buy of 18,551, and the sentence gets believed over the number.
 */
export function coverVerdict(
  useStock: boolean,
  buyQty: number,
  poolLocation: string,
  shortfall: CoverageShortfall | null = null,
): { tone: 'stock' | 'buy'; headline: string; note: string | null } {
  if (useStock) {
    if (shortfall) {
      const short = Math.round(shortfall.qty).toLocaleString('en-MY');
      return {
        tone: 'stock',
        headline: 'Committed demand is covered',
        note: `Below the reorder point by ${short}${
          poolLocation ? ` across ${poolLocation}` : ''
        }`,
      };
    }
    return {
      tone: 'stock',
      headline: poolLocation ? `Use the pool (${poolLocation})` : 'Use existing stock',
      note: null,
    };
  }
  return { tone: 'buy', headline: `Buy ${buyQty.toLocaleString('en-MY')}`, note: null };
}
