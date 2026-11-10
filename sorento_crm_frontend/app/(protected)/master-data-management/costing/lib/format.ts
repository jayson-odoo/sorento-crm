/**
 * Costing display and draft maths. Full precision inside, 2 dp half-up only at the edge
 * (CONTRACT section 1). The recompute here is the same formula as the backend's `formula.py`, so
 * the figures move while a cell is typed and match the saved result.
 */
import { formatDateInMalaysia } from '@/lib/helpers';
import type { CostingReason, CostingRow, CostMethod, TransportMode } from '../types/costing.types';

export const METHOD_LABEL: Record<CostMethod, string> = {
  primary: 'Primary supplier',
  selected: 'Selected supplier',
  average: 'Average of supplier prices',
  last_po: 'Last PO price',
};

export const TRANSPORT_LABEL: Record<TransportMode, string> = { add: 'Add', multiply: 'Multiply' };

const GROUP = /\B(?=(\d{3})+(?!\d))/g;

/** 2 dp, half up, thousands separated: 1861.6125 -> "1,861.61". Null is not a number: "-". */
export function money(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '-';
  const negative = value < 0;
  // 6 dp first: the API's own precision, which strips binary noise (2.675 is 2.675000).
  const [whole, frac = ''] = Math.abs(value).toFixed(6).split('.');
  let cents = BigInt(whole) * BigInt(100) + BigInt(frac.slice(0, 2));
  if (frac.charAt(2) >= '5') cents += BigInt(1);
  const text = cents.toString().padStart(3, '0');
  const int = text.slice(0, -2).replace(GROUP, ',');
  return `${negative && cents > BigInt(0) ? '-' : ''}${int}.${text.slice(-2)}`;
}

/** A percentage with 2 dp: "130.61 %". */
export function percent(value: number | null | undefined): string {
  return value === null || value === undefined ? '-' : `${money(value)} %`;
}

/** Up to `dp` places with trailing zeros dropped: 1.6, 0.2273, 1. */
export function trimmed(value: number | null | undefined, dp = 4): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '-';
  return String(Number(value.toFixed(dp)));
}

/** "2026-11-11" -> "11/11/2026": the repo's one date shape, via the shared helper. */
export function shortDate(iso: string | null | undefined): string {
  return iso ? formatDateInMalaysia(iso) || iso : '-';
}

export function reasonText(reason: CostingReason): string {
  switch (reason.code) {
    case 'no_cost':
      return 'No cost';
    case 'no_rate':
      return `No rate for ${reason.currency ?? ''} on ${shortDate(reason.date)}`;
    case 'no_primary':
      return 'Set a primary supplier';
    case 'selected_not_linked':
      return 'Selected supplier no longer linked';
    case 'no_po_price':
      return 'No PO price';
    case 'no_transport_rule':
      return 'No transport rule';
  }
}

/** "+ RM 8.00" or "x 1.07"; null without a rule. */
export function transportText(mode: TransportMode | null, value: number | null): string | null {
  if (!mode || value === null) return null;
  return mode === 'add' ? `+ RM ${money(value)}` : `x ${trimmed(value)}`;
}

export interface Figures {
  landing: number | null;
  final: number | null;
  margin: number | null;
  /** The mark-up in force: the party's or the row's, or in the standard view the achieved one. */
  markup: number | null;
}

/**
 * Landing, Final, Margin and Mark-up for a draft. `draft.markup` is the typed row mark-up (party
 * view), null when none is typed. In the Company standard view Final is the list price and
 * Mark-up the achieved one.
 * `draft.transport` is null when the draft keeps the inherited rule: the row's own landing is then
 * already right and only the mark-up moves.
 */
export function figuresFor(
  row: CostingRow,
  draft: {
    transport: { mode: TransportMode; value: number } | null;
    /** The typed row mark-up; null when none is typed (the party's applies). */
    markup: number | null;
    /** The party's own mark-up. */
    inheritedMarkup: number | null;
  },
  view: 'standard' | 'party',
): Figures {
  let landing = row.landing;
  if (draft.transport && row.unit_cost !== null && row.rate_to_base !== null) {
    const base = row.unit_cost * row.rate_to_base * row.sst_factor;
    landing = draft.transport.mode === 'add' ? base + draft.transport.value : base * draft.transport.value;
  }
  if (view === 'standard') {
    const achieved =
      landing !== null && landing !== 0 && row.list_price !== null
        ? ((row.list_price - landing) / landing) * 100
        : null;
    return { landing, final: row.final, margin: null, markup: achieved };
  }
  const markup = draft.markup ?? draft.inheritedMarkup;
  if (landing === null || markup === null) return { landing, final: null, margin: null, markup };
  const final = landing * (1 + markup / 100);
  const margin = row.list_price !== null && final !== 0 ? ((row.list_price - final) / final) * 100 : null;
  return { landing, final, margin, markup };
}
