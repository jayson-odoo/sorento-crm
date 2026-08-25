import { fromMinor, toMinor } from './supplyComposition';
import type { BoardCell, BoardContribution, BoardSource } from '../types/fulfilmentPlanning.types';

/**
 * What the ladder proposes for a whole cell, said as quantities by KIND OF SOURCE.
 *
 * The dialog opens on a decision, so the decision leads: the kinds with a quantity, in this
 * fixed order. ONLY the kinds with a quantity, since 25 August 2026 - the card used to state
 * all four always, muting the empty ones, and on a real cell three of the four read 0, so the
 * one line that said what to do sat inside three lines of nothing and had to be found each
 * time. The fixed ORDER is what keeps the card readable between cells; a row of zero was
 * never what did that.
 *
 * THE LABELS ARE NOT THE RUNG NAMES. The engine's vocabulary (`pool`, `group_take`,
 * `group_borrow`, `cross_group_borrow`, `buy` - `app/services/scm/front_planning_engine.py`)
 * is about which rule fired; the planner is deciding about WHERE the stock comes from. The
 * mapping, and the evidence in the ladder for each:
 *
 * | Row                   | Rungs                                    | Condition |
 * | --------------------- | ---------------------------------------- | --------- |
 * | Buy                   | `buy`                                    | always - "it is not held anywhere yet" |
 * | Use shared stock      | `pool`, `group_take`, `group_borrow`     | the source's site is NOT this line's |
 * | Use own location      | `pool`, `group_take`, `group_borrow`     | the source's site IS this line's |
 * | Borrow other location | `cross_group_borrow`                     | always - by definition outside the group |
 * | Incoming supply       | `incoming` (`timely_spo`)                | only when there is some |
 *
 * The own/shared split is on the SITE, not the warehouse code, because rung 2 is "the shared
 * pool(s), OWN SITE FIRST" and a pool is named by its site (`BRW`) while a line is fulfilled
 * from a warehouse in it (`BRW-BB`). Comparing the codes would read a line's own pool as
 * somebody else's stock. Rung 3 (`group_take`) is documented as "never this line's own", so it
 * lands on shared by the same rule rather than by a special case; rung 4 (`group_borrow`) can
 * be either, and at the line's own warehouse it is exactly the captain's "the agent's other
 * customers' stock there".
 *
 * INCOMING IS ITS OWN ROW and is never folded into Buy: it is already bought and on its way,
 * so adding it to Buy would propose buying it twice. It is last, and only when a cell has any,
 * because it is not one of the four decisions.
 */
export interface SuggestionRow {
  key: string;
  label: string;
  /** The quantity, summed across every line of the cell. `'0'` when this row is empty. */
  qty: string;
  /** Where it comes from, each named once, in the order the ladder took them. */
  locations: string[];
  /**
   * The engine's own sentence for this row, when every source on it gives the SAME one.
   *
   * It is what makes a Buy readable: "delivery date beyond the lead time window; stock kept
   * for nearer orders" and "nothing free at any location" are the same quantity for opposite
   * reasons, and the card is where the planner decides between them. Two different sentences
   * on one row is a per-line fact, and the table below is where per-line facts live, so the
   * row says nothing rather than picking one of them.
   */
  note?: string;
}

const BUY = 'buy';
const SHARED = 'shared';
const OWN = 'own';
const BORROW_OTHER = 'borrow_other';
const INCOMING = 'incoming';

const LABELS: Record<string, string> = {
  [BUY]: 'Buy',
  [SHARED]: 'Use shared stock',
  [OWN]: 'Use own location',
  [BORROW_OTHER]: 'Borrow other location',
  [INCOMING]: 'Incoming supply',
};

/** The four decisions, in the order they are read. */
const ORDER = [BUY, SHARED, OWN, BORROW_OTHER];

/**
 * The site a warehouse code belongs to: `BRW-BB` and `BRW-HP` are both at `BRW`.
 *
 * The ownership-group suffix is what makes two codes different warehouses; the prefix is the
 * physical site, and it is what the pool rung is named by.
 */
function siteOf(code: string | null | undefined): string {
  if (!code) return '';
  return code.split('-')[0].trim().toUpperCase();
}

/** Which row this source belongs on. See the table in the module docstring. */
function rowOf(source: BoardSource, contribution: BoardContribution): string | null {
  if (source.kind === 'buy') return BUY;
  if (source.kind === 'timely_spo') return INCOMING;
  // A line whose sales order names no location was never walked down the ladder at all, so it
  // proposes nothing rather than proposing a buy nobody decided.
  if (source.kind === 'unplannable') return null;
  if (source.rung === 'cross_group_borrow') return BORROW_OTHER;
  const at = siteOf(source.location);
  if (at && at === siteOf(contribution.fulfilment_location)) return OWN;
  return SHARED;
}

export function suggestionBreakdown(
  cell: Pick<BoardCell, 'contributions'>,
): SuggestionRow[] {
  const minor = new Map<string, number>();
  const where = new Map<string, string[]>();
  const why = new Map<string, Set<string>>();
  for (const key of [...ORDER, INCOMING]) {
    minor.set(key, 0);
    where.set(key, []);
    why.set(key, new Set());
  }

  for (const contribution of cell.contributions) {
    for (const source of contribution.sources) {
      const key = rowOf(source, contribution);
      if (!key) continue;
      minor.set(key, (minor.get(key) ?? 0) + toMinor(source.qty));
      const at = source.location;
      const seen = where.get(key) as string[];
      if (at && !seen.includes(at)) seen.push(at);
      if (source.reason) (why.get(key) as Set<string>).add(source.reason);
    }
  }

  const rowFor = (key: string): SuggestionRow => {
    const reasons = [...(why.get(key) ?? [])];
    return {
      key,
      label: LABELS[key],
      qty: fromMinor(minor.get(key) ?? 0),
      locations: where.get(key) ?? [],
      ...(reasons.length === 1 ? { note: reasons[0] } : {}),
    };
  };

  // Only what the ladder actually proposes. `Incoming supply` was already conditional on
  // having a quantity; the other four now follow the same rule rather than a different one.
  const rows = [...ORDER, INCOMING]
    .filter((key) => (minor.get(key) ?? 0) !== 0)
    .map(rowFor);

  return rows;
}
