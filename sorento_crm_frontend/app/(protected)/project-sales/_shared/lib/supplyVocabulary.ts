/**
 * ONE vocabulary for where supply comes from, used by the board grid, the board list, the cell
 * popover and the SO detail (PLAN-scm-cs-planning-uat.md section 2).
 *
 * WHAT DECIDES THE WORDS IS THE ENGINE'S `rung`, NEVER A WAREHOUSE CODE. This file was
 * `boardSuggestion.ts` and it split own/shared on the SITE PREFIX: a pool draw from `BRW` on a
 * line fulfilled from `BRW-BB` shared the prefix, so the shared pool read as "Use own location".
 * The captain, on the live cell: "Use own location, 71 from BRW reads wrong. Own location is the
 * line's -BB location. BRW is the SHARED pool." The prefix is a coincidence of naming; the rung
 * is the rule that actually fired, and it is the only input here.
 *
 * | Rung                 | Label                      | Colour  |
 * | -------------------- | -------------------------- | ------- |
 * | `group_take`         | Use own location           | emerald |
 * | `pool`               | Use shared stock           | sky     |
 * | `group_borrow`       | Borrow from another order  | amber   |
 * | `cross_group_borrow` | Borrow other location      | amber   |
 * | `buy`                | Buy                        | rose    |
 * | `incoming`           | Incoming supply            | violet  |
 *
 * The rung strings are `app/services/scm/front_planning_engine.py`'s own constants
 * (`RUNG_POOL`, `RUNG_GROUP_TAKE`, ...), spelled here exactly as the engine spells them.
 *
 * A COMPONENT THAT CARRIES NO RUNG IS READ ON THE OWNERSHIP GROUP, never on the site and never
 * on the exact code. Verified against the live board on 25 Aug: every source and every decision
 * row of a COVERED line arrives with `rung: null` (the board rebuilds a frozen composition
 * without it), so this fallback is what SO324132 rev 1 is actually rendered by. See
 * `fallbackRung`.
 *
 * INCOMING IS ITS OWN KIND and is never folded into Buy: it is already bought and on its way,
 * so adding it to Buy would propose buying it twice.
 */
import { fromMinor, toMinor } from './supplyComposition';
import type {
  BoardCell,
  BoardContribution,
  BoardDecision,
  BoardLineDecision,
} from '../types/fulfilmentPlanning.types';

export type SupplyKind =
  | 'buy'
  | 'shared'
  | 'own'
  | 'borrow_order'
  | 'borrow_other'
  | 'incoming';

/** What a person reads. The whole product says supply in these six words and no others. */
export const LABELS: Record<SupplyKind, string> = {
  buy: 'Buy',
  shared: 'Use shared stock',
  own: 'Use own location',
  borrow_order: 'Borrow from another order',
  borrow_other: 'Borrow other location',
  incoming: 'Incoming supply',
};

/**
 * The same six, short enough for a grid cell and a summary line ("Shared 71 · Buy 0").
 *
 * A cell is 150px wide; "Borrow from another order 71" does not fit in it, and truncating the
 * label would leave two kinds reading the same. The long form is the legend's and the card's.
 */
export const SHORT_LABELS: Record<SupplyKind, string> = {
  buy: 'Buy',
  shared: 'Shared',
  own: 'Own',
  borrow_order: 'Borrow (order)',
  borrow_other: 'Borrow (other)',
  incoming: 'Incoming',
};

/**
 * Tailwind class tokens per kind: the paint for a bar segment or a legend swatch, and the
 * matching text colour for the word beside it.
 *
 * Both borrow kinds are amber, as the vocabulary table says. They are told apart by their
 * label, not by their shade: two borrows are the same decision made against different stock.
 */
export const COLOURS: Record<SupplyKind, { bar: string; text: string }> = {
  buy: { bar: 'bg-rose-500', text: 'text-rose-700' },
  shared: { bar: 'bg-sky-500', text: 'text-sky-700' },
  own: { bar: 'bg-emerald-500', text: 'text-emerald-700' },
  borrow_order: { bar: 'bg-amber-500', text: 'text-amber-700' },
  borrow_other: { bar: 'bg-amber-500', text: 'text-amber-700' },
  incoming: { bar: 'bg-violet-500', text: 'text-violet-700' },
};

/**
 * The fixed reading order. What keeps a card or a bar comparable between two cells is that
 * Buy is always in the same place, whether it is 300 or absent.
 */
export const ORDER: SupplyKind[] = [
  'buy',
  'shared',
  'own',
  'borrow_order',
  'borrow_other',
  'incoming',
];

/**
 * One piece of supply, in the shape both wire types already have.
 *
 * Structural rather than a union of `BoardSource | SupplyComponent`, because the two name the
 * warehouse differently (`location` / `source_location`) and are otherwise the same three
 * facts. Anything with a kind, a rung and a quantity can be described.
 */
export interface SupplyPart {
  kind?: string | null;
  rung?: string | null;
  qty: string;
  location?: string | null;
  /** `SupplyComponent`'s own spelling of `location`. */
  source_location?: string | null;
}

function locationOf(part: SupplyPart): string | null {
  return part.location ?? part.source_location ?? null;
}

/**
 * The ownership-group suffix a warehouse code carries: `BRW-BB` -> `BB`.
 *
 * THE SUFFIX AFTER THE FIRST HYPHEN, upper-cased, which is the backend's own rule
 * (`app/services/scm/sales_agent_service.group_of_warehouse_code`) spelled the same way here so
 * the two cannot drift. A plain site code (`BRW`, `MWH`, `DC1`, `WH3`, `RSW`) has no hyphen and
 * therefore no group: it is a POOL, not anyone's ownership group.
 */
function groupOf(code: string | null | undefined): string | null {
  if (!code) return null;
  const text = String(code).trim();
  const cut = text.indexOf('-');
  if (cut < 0) return null;
  return text.slice(cut + 1).trim().toUpperCase() || null;
}

/**
 * The rung a component with none of its own would have been produced by.
 *
 * A COVERED line's sources and every decision reserve row arrive with `rung: null` - verified
 * against the live board on 25 Aug: SO324132 rev 1's CWCY605 sends three reserve sources at
 * DC1-BB / MWH-BB / WH3-BB, all `rung: null`, because `_apply_frozen` rebuilds a frozen
 * composition without carrying the rung the engine froze. An uncovered line on the same board
 * carries `pool` / `buy` / `cross_group_borrow` correctly.
 *
 * So the fallback has to reproduce the ladder's own reading, and it is the OWNERSHIP GROUP that
 * does it, never the site. For a `BRW-BB` line, `DC1-BB` is the agent's OWN group at another
 * site - rung 2, "Use own location" - while `BRW` is the shared pool at this line's own site.
 * Comparing the exact code called DC1-BB somebody else's stock; comparing the site prefix called
 * BRW the line's own. The group suffix is the only comparison that reads both correctly.
 */
function fallbackRung(location: string | null, ownLocation: string | null | undefined): string {
  const group = groupOf(location);
  // No hyphen at all: a site pool (BRW / MWH / DC1 / WH3 / RSW), shared by every group there.
  if (!group) return 'pool';
  if (group === groupOf(ownLocation)) return 'group_take';
  // A warehouse in somebody ELSE's ownership group. Not the agent's to take, so it is a borrow.
  return 'cross_group_borrow';
}

/**
 * Which kind this piece of supply is. The rung decides; the code never does.
 *
 * `kind` is consulted only where there is no rung to consult: Buy and incoming carry their own
 * kind, and a component frozen before ladder v2 carries no rung at all (`SupplyComponent.rung`
 * is optional for exactly that reason). An unrunged reserve reads as shared and an unrunged
 * borrow as borrow-other - the widest reading of each, so nothing claims the agent's own group
 * holds stock the record does not say it holds.
 */
export function rowOf(part: SupplyPart, ownLocation?: string | null): SupplyKind | null {
  // A line whose sales order names no location was never walked down the ladder at all, so it
  // proposes nothing rather than proposing a buy nobody decided.
  if (part.kind === 'unplannable') return null;
  const rung =
    part.rung ??
    (part.kind === 'reserve' || part.kind === 'borrow'
      ? fallbackRung(locationOf(part), ownLocation)
      : null);
  switch (rung) {
    case 'buy':
      return 'buy';
    case 'incoming':
      return 'incoming';
    case 'pool':
      return 'shared';
    case 'group_take':
      return 'own';
    case 'group_borrow':
      return 'borrow_order';
    case 'cross_group_borrow':
      return 'borrow_other';
    default:
      break;
  }
  if (part.kind === 'buy') return 'buy';
  if (part.kind === 'timely_spo') return 'incoming';
  return null;
}

/** One kind's share of a composition. The unit the bar and the legend are drawn from. */
export interface SupplySegment {
  kind: SupplyKind;
  qty: string;
}

/** The same, with the locations it was drawn from and how much came from each. */
export interface SupplyPlace {
  location: string;
  qty: string;
}

/**
 * A composition reduced to its kinds, in `ORDER`, keeping only the kinds with a quantity.
 *
 * A row of zero was never what made a card readable between cells - the fixed order is - and on
 * a real cell three of six kinds read 0, so the one line that said what to do sat inside five
 * lines of nothing and had to be found each time.
 */
export function segmentsOf(
  parts: SupplyPart[],
  ownLocation?: string | null,
): SupplySegment[] {
  const minor = new Map<SupplyKind, number>();
  for (const part of parts) {
    const kind = rowOf(part, ownLocation);
    if (!kind) continue;
    minor.set(kind, (minor.get(kind) ?? 0) + toMinor(part.qty));
  }
  return ORDER.filter((kind) => (minor.get(kind) ?? 0) !== 0).map((kind) => ({
    kind,
    qty: fromMinor(minor.get(kind) as number),
  }));
}

/**
 * The largest segment: what a cell says in one phrase when it has room for one phrase.
 *
 * Ties break on `ORDER`, so two equal halves always name the same one of the two rather than
 * whichever the map happened to yield first.
 */
export function dominant(segments: SupplySegment[]): SupplySegment | null {
  let best: SupplySegment | null = null;
  for (const segment of segments) {
    if (!best || toMinor(segment.qty) > toMinor(best.qty)) best = segment;
  }
  return best;
}

/** "Shared 71". The dominant kind in the fewest words that still name it. */
export function dominantText(segments: SupplySegment[]): string {
  const best = dominant(segments);
  return best ? `${SHORT_LABELS[best.kind]} ${best.qty}` : '';
}

/**
 * A composition as one compact line: "Shared 71 (BRW) · Buy 12".
 *
 * Only the kinds with a quantity, for the reason `segmentsOf` gives, and each kind names the
 * locations it drew on so "Shared 71" cannot be read as "shared from nowhere in particular".
 * Empty composition returns an empty string; the caller says what nothing means on its screen.
 */
export function describe(parts: SupplyPart[], ownLocation?: string | null): string {
  const places = placesOf(parts, ownLocation);
  return segmentsOf(parts, ownLocation)
    .map((segment) => {
      const where = (places.get(segment.kind) ?? [])
        .map((place) => place.location)
        .join(', ');
      return where
        ? `${SHORT_LABELS[segment.kind]} ${segment.qty} (${where})`
        : `${SHORT_LABELS[segment.kind]} ${segment.qty}`;
    })
    .join(' · ');
}

/** Per kind, how much came from each named location, in the order the ladder took them. */
function placesOf(
  parts: SupplyPart[],
  ownLocation?: string | null,
): Map<SupplyKind, SupplyPlace[]> {
  const byKind = new Map<SupplyKind, Map<string, number>>();
  for (const part of parts) {
    const kind = rowOf(part, ownLocation);
    if (!kind) continue;
    const at = locationOf(part);
    if (!at) continue;
    const seen = byKind.get(kind) ?? new Map<string, number>();
    seen.set(at, (seen.get(at) ?? 0) + toMinor(part.qty));
    byKind.set(kind, seen);
  }
  const out = new Map<SupplyKind, SupplyPlace[]>();
  for (const [kind, seen] of byKind) {
    out.set(
      kind,
      [...seen].map(([location, qty]) => ({ location, qty: fromMinor(qty) })),
    );
  }
  return out;
}

/**
 * What the ladder proposes for a whole cell, said as quantities by kind of source.
 *
 * The dialog opens on a decision, so the decision leads: the kinds with a quantity, in `ORDER`.
 */
export interface SuggestionRow {
  key: SupplyKind;
  label: string;
  /** The quantity, summed across every line of the cell. */
  qty: string;
  /**
   * Where it came from AND HOW MUCH FROM EACH ("454 from DC1-BB, 267 from MWH-BB").
   *
   * A bare list of codes was the whole of it, so a row reading "932 from DC1-BB, MWH-BB,
   * WH3-BB" left the planner to guess the split - and the split is the instruction: it is
   * three separate movements of stock, and somebody has to key each of them.
   */
  places: SupplyPlace[];
  /**
   * The engine's own sentence for this row, when every source on it gives the SAME one.
   *
   * It is what makes a Buy readable: "delivery date beyond the lead time window; stock kept
   * for nearer orders" and "nothing free at any location" are the same quantity for opposite
   * reasons, and the card is where the planner decides between them. Two different sentences
   * on one row is a per-line fact, and the table below the card is where per-line facts live,
   * so the row says nothing rather than picking one of them.
   */
  note?: string;
}

/** "454 from DC1-BB, 267 from MWH-BB, 211 from WH3-BB", or the bare total when Buy. */
export function rowText(row: SuggestionRow): string {
  if (row.places.length === 0) return row.qty;
  return row.places.map((place) => `${place.qty} from ${place.location}`).join(', ');
}

export function suggestionBreakdown(cell: Pick<BoardCell, 'contributions'>): SuggestionRow[] {
  // Resolved PER CONTRIBUTION, because a cell spans lines whose own locations need not agree:
  // `DC1-BB` is the agent's own group on a `BRW-BB` line and somebody else's on a `BRW-IB` one.
  // Each part is re-stamped with the rung its own line resolved it at, so everything below can
  // aggregate the flat list without needing to know which line each part came from.
  const parts: SupplyPart[] = [];
  const why = new Map<SupplyKind, Set<string>>();
  for (const contribution of cell.contributions) {
    for (const source of contribution.sources) {
      const kind = rowOf(source, contribution.fulfilment_location);
      if (!kind) continue;
      parts.push({
        kind: source.kind,
        rung: rungFor(kind),
        qty: source.qty,
        location: source.location ?? null,
      });
      if (!source.reason) continue;
      const seen = why.get(kind) ?? new Set<string>();
      seen.add(source.reason);
      why.set(kind, seen);
    }
  }

  const places = placesOf(parts);
  return segmentsOf(parts).map((segment) => {
    const reasons = [...(why.get(segment.kind) ?? [])];
    return {
      key: segment.kind,
      label: LABELS[segment.kind],
      qty: segment.qty,
      places: places.get(segment.kind) ?? [],
      ...(reasons.length === 1 ? { note: reasons[0] } : {}),
    };
  });
}

/**
 * A confirmed or drafted decision, read as supply parts.
 *
 * A DECISION CARRIES NO RUNG on its reserve rows (`BoardReserveComponent` is a warehouse and a
 * quantity), so the rung is looked up from the line's own `sources` by warehouse - which is
 * where an amendment's reserve rows come from in the first place: `BoardAmendDialog` only edits
 * the quantities of the rows the proposal named. A row with no match at all falls back to an
 * EXACT code comparison with the line's own location, which is a different test from the site
 * prefix that caused this file to be rewritten: `BRW-BB` is literally the line's warehouse,
 * `BRW` is literally not.
 *
 * Borrow rows carry their rung when the server froze them; a drafted borrow names its donor
 * sales order instead, and a borrow that names one IS the borrow-from-another-order kind.
 */
export function decisionParts(
  contribution: BoardContribution,
  decision: BoardLineDecision | BoardDecision,
): SupplyPart[] {
  /** The two decision shapes' reserve and borrow rows, read on what they have in common. */
  type ReserveRow = { warehouse_id?: string | null; location?: string | null; qty: string };
  type BorrowRow = {
    qty: string;
    location?: string | null;
    warehouse_code?: string | null;
    rung?: string | null;
    donor_so_number?: string | null;
  };

  const rungByLocation = new Map<string, string>();
  const rungByWarehouse = new Map<string, string>();
  for (const source of contribution.sources) {
    if (!source.rung) continue;
    if (source.location) rungByLocation.set(source.location, source.rung);
    if (source.warehouse_id) rungByWarehouse.set(source.warehouse_id, source.rung);
  }
  const parts: SupplyPart[] = [];

  const incoming = decision.timely_spo_qty;
  if (incoming !== undefined && toMinor(incoming) !== 0) {
    parts.push({ kind: 'timely_spo', rung: 'incoming', qty: incoming });
  }

  for (const row of (decision.reserve ?? []) as ReserveRow[]) {
    // A rung the line's own sources already state beats any reading of the code. When there is
    // none - which is EVERY covered line, since the board rebuilds a frozen composition without
    // it - the row is left unrunged and `rowOf` resolves it on the ownership group.
    const rung =
      (row.warehouse_id ? rungByWarehouse.get(row.warehouse_id) : undefined) ??
      (row.location ? rungByLocation.get(row.location) : undefined) ??
      null;
    parts.push({ kind: 'reserve', rung, qty: row.qty, location: row.location ?? null });
  }

  for (const row of (decision.borrow ?? []) as BorrowRow[]) {
    // A borrow that names a donor sales order IS the borrow-from-another-order kind, whatever
    // warehouse it sits in. Without one, `rowOf` resolves it on the group like a reserve.
    const rung = row.rung ?? (row.donor_so_number ? 'group_borrow' : null);
    parts.push({
      kind: 'borrow',
      rung,
      qty: row.qty,
      location: row.location ?? row.warehouse_code ?? null,
    });
  }

  const buy = decision.buy_qty;
  if (buy !== undefined && toMinor(buy) !== 0) {
    parts.push({ kind: 'buy', rung: 'buy', qty: buy });
  }

  return parts;
}

/**
 * What ONE contributing line's bar is drawn from, and whether it is settled.
 *
 * The DECISION when there is one - a confirmed active revision, or an amendment ticked into
 * this session's draft - and the engine's proposal otherwise. So a line the planner amends from
 * Buy to the shared pool flips rose to sky the moment the tick lands, and back when it is
 * cleared, with no second copy of the draft anywhere.
 *
 * A REJECTION decides no supply, so it leaves the proposal on screen and leaves it faded: there
 * is nothing settled to draw solid.
 */
export function contributionSupply(
  contribution: BoardContribution,
  drafted?: BoardDecision | null,
): { segments: SupplySegment[]; decided: boolean } {
  if (drafted && drafted.verdict !== 'rejected') {
    const composed = drafted.reserve || drafted.borrow || drafted.buy_qty !== undefined;
    const parts = composed
      ? decisionParts(contribution, drafted)
      : contribution.sources;
    return {
      segments: segmentsOf(parts, contribution.fulfilment_location),
      decided: true,
    };
  }
  if (!drafted && contribution.covered && contribution.decision) {
    return {
      segments: segmentsOf(
        decisionParts(contribution, contribution.decision),
        contribution.fulfilment_location,
      ),
      decided: true,
    };
  }
  return {
    segments: segmentsOf(contribution.sources, contribution.fulfilment_location),
    decided: false,
  };
}

/**
 * The whole cell's bar: every contributing line's supply, summed by kind.
 *
 * Solid only when EVERY contribution is settled. A cell half decided and half proposed is not
 * a decision, and drawing it solid would say it was.
 */
export function cellSupply(
  cell: Pick<BoardCell, 'contributions'>,
  draft: Record<string, BoardDecision>,
): { segments: SupplySegment[]; decided: boolean } {
  const parts: SupplyPart[] = [];
  let decided = cell.contributions.length > 0;
  for (const contribution of cell.contributions) {
    const supply = contributionSupply(contribution, draft[contribution.key] ?? null);
    if (!supply.decided) decided = false;
    for (const segment of supply.segments) {
      parts.push({ kind: segment.kind, rung: rungFor(segment.kind), qty: segment.qty });
    }
  }
  return { segments: segmentsOf(parts), decided };
}

/** The rung a kind came from, so a summed segment can be re-read by `rowOf` unchanged. */
function rungFor(kind: SupplyKind): string {
  switch (kind) {
    case 'buy':
      return 'buy';
    case 'shared':
      return 'pool';
    case 'own':
      return 'group_take';
    case 'borrow_order':
      return 'group_borrow';
    case 'borrow_other':
      return 'cross_group_borrow';
    case 'incoming':
      return 'incoming';
  }
}
