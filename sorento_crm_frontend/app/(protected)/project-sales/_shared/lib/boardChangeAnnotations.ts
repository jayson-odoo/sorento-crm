/**
 * What a re-uploaded sales-order book did to a line, said on the board cell that line sits in
 * (`PLAN-scm-cs-planning-uat.md` part 3, AC-P3-2 / AC-P3-3).
 *
 * The captain, 25 August 2026: "same page as fulfilment, with the change annotated" - and
 * structure, not a sentence. So a changed line reads as a small Was / Now table of three rows
 * (Qty, Date, Decision) and nothing else.
 *
 * TWO RULES THIS FILE EXISTS TO HOLD:
 *
 * 1. **The batch's own vocabulary never reaches the screen.** `keep` / `release` / `replan` /
 *    `reduce` / `retire` are how the rule table names a reaction to itself; a planner reads
 *    supply in six words and no others (`supplyVocabulary.ts`). So the Decision row is built
 *    from the line's HELD composition on the Was side and its fresh PROPOSAL on the Now side,
 *    through the same `partsBreakdown` the Suggestion and Decision cards are built from.
 * 2. **A closed line still has to be visible.** It contributes nothing to the board any more -
 *    the book closed it - so it has no cell of its own, and dropping it would make two thirds
 *    of the fixture's change invisible. It is annotated on the surviving cell of the SAME
 *    product on the SAME sales order instead, and reads `Closed` in the Now column, which is
 *    where a planner is already looking to see what replaced it.
 *
 * Pure: no fetch, no clock, no React. The panel hands it the batch and the cells it is about
 * to render, and gets back the annotations keyed exactly as the matrix keys its cells.
 */
import { LABELS, partsBreakdown, rowText, type SupplyPart } from './supplyVocabulary';
import type { BoardCell, BoardContribution } from '../types/fulfilmentPlanning.types';
import type {
  PlanningChangeBatch,
  PlanningChangeHeld,
  PlanningChangeRow,
} from '../types/planningChange.types';

/** One side of the Was / Now table. `null` on a value the row cannot state. */
export interface BoardChangeSide {
  qty: string | null;
  date: string | null;
  /** The supply decision in board words, e.g. `Buy 25` or `Use own location 40 from BRW-BB`. */
  decision: string | null;
}

/** What one changed line reads on its cell. */
export interface BoardChangeAnnotation {
  /** The batch row this came from - the id a decision is PUT against. */
  rowId: string;
  soNumber: string;
  lineNo: number;
  itemCode: string;
  /** The book's own change kind, for the caption. Never a reaction verb. */
  kind: PlanningChangeRow['kind'];
  /** The line is closed in the book: the Now column reads `Closed` and states no quantity. */
  closed: boolean;
  was: BoardChangeSide;
  now: BoardChangeSide;
  /** `10 moved BRW -> BRW-IB, line cancelled` (AC-P3-9), or null. */
  movedTransfer: string | null;
  /** Which line the change is about, when the batch knows it. Used to match a cell's lines. */
  projectLineId: string | null;
}

/** How the matrix keys a cell: the row's key (item code, or an id on a pivoted axis). */
export function cellKeyOf(cell: Pick<BoardCell, 'item_code' | 'row_key' | 'bucket_key'>): string {
  return `${cell.row_key ?? cell.item_code}|${cell.bucket_key}`;
}

/** The composition a line HELD before the book moved, as supply parts. */
function heldParts(held: PlanningChangeHeld | null | undefined): SupplyPart[] {
  if (!held) return [];
  const parts: SupplyPart[] = [];
  for (const reserve of held.reserve ?? []) {
    parts.push({ kind: 'reserve', qty: reserve.qty, location: reserve.location });
  }
  for (const borrow of held.borrow ?? []) {
    parts.push({ kind: 'borrow', qty: borrow.qty, location: borrow.location });
  }
  if (Number(held.timely_spo_qty ?? '0') > 0) {
    parts.push({ kind: 'timely_spo', qty: held.timely_spo_qty });
  }
  if (Number(held.buy_qty ?? '0') > 0) parts.push({ kind: 'buy', qty: held.buy_qty });
  return parts;
}

/**
 * Board words for one composition: `Use own location 40 from BRW-BB · Buy 25`.
 *
 * Through `partsBreakdown`, so the annotation, the Suggestion card and the cell's own bar all
 * say the same thing about the same parts.
 */
export function decisionWords(
  parts: SupplyPart[],
  ownLocation?: string | null,
): string | null {
  if (parts.length === 0) return null;
  const rows = partsBreakdown([{ parts, ownLocation }]);
  if (rows.length === 0) return null;
  return rows.map((row) => `${LABELS[row.key]} ${rowText(row)}`).join(' · ');
}

/**
 * The Now side's decision: what the batch proposes for the line at its new date.
 *
 * The row's own frozen `proposal` when it carries one (a `replan` / `qty_up` row always does),
 * else the composition the row was decided with, else what it held - a line whose reaction
 * changes nothing about its supply reads the same decision on both sides, which is the honest
 * answer rather than a blank.
 */
function proposedParts(row: PlanningChangeRow): SupplyPart[] {
  if (row.proposal) {
    const proposal = row.proposal as BoardContribution;
    return proposal.proposed?.components ?? proposal.sources ?? [];
  }
  if (row.composition) {
    const parts: SupplyPart[] = [];
    for (const reserve of row.composition.reserve ?? []) {
      parts.push({ kind: 'reserve', qty: reserve.qty, location: reserve.warehouse_id });
    }
    for (const borrow of row.composition.borrow ?? []) {
      parts.push({ kind: 'borrow', qty: borrow.qty, location: borrow.warehouse_id });
    }
    if (Number(row.composition.timely_spo_qty ?? '0') > 0) {
      parts.push({ kind: 'timely_spo', qty: row.composition.timely_spo_qty });
    }
    if (Number(row.composition.buy_qty ?? '0') > 0) {
      parts.push({ kind: 'buy', qty: row.composition.buy_qty });
    }
    return parts;
  }
  return heldParts(row.held);
}

/** One batch row turned into what its cell reads. */
export function annotationOf(
  row: PlanningChangeRow,
  soNumber: string,
  ownLocation?: string | null,
): BoardChangeAnnotation {
  const closed = row.kind === 'closed';
  const proposal = (row.proposal ?? null) as BoardContribution | null;
  const location = ownLocation ?? proposal?.fulfilment_location ?? null;
  const lineId = row.project_line_id ?? proposal?.project_line_id ?? null;
  return {
    rowId: row.id,
    soNumber,
    lineNo: row.line_no,
    itemCode: row.item_code,
    kind: row.kind,
    closed,
    was: {
      qty: row.from?.qty ?? null,
      date: row.from?.required_date ?? null,
      decision: decisionWords(heldParts(row.held), location),
    },
    now: {
      qty: closed ? null : row.to?.qty ?? null,
      date: closed ? null : row.to?.required_date ?? null,
      decision: closed ? null : decisionWords(proposedParts(row), location),
    },
    movedTransfer: row.moved_transfer ?? null,
    projectLineId: lineId,
  };
}

/**
 * Every annotation the board should draw, keyed by the cell it belongs on.
 *
 * A row lands on the cell whose lines include the row's own project line. Failing that - the
 * closed case, where the line has left the board - it lands on the FIRST cell of the same
 * product on the same sales order, so what replaced it and what it was are read together. A
 * row whose product is nowhere in the selection is dropped: there is no cell to draw it on.
 */
export function annotationsByCell(
  batch: Pick<PlanningChangeBatch, 'orders'> | null | undefined,
  cells: BoardCell[],
): Map<string, BoardChangeAnnotation[]> {
  const out = new Map<string, BoardChangeAnnotation[]>();
  if (!batch) return out;

  /** Which cell key each project line contributes to, and each (SO, item) pair sits in. */
  const cellByLine = new Map<string, string>();
  const locationByLine = new Map<string, string | null>();
  const cellByOrderItem = new Map<string, string>();
  for (const cell of cells) {
    const key = cellKeyOf(cell);
    for (const contribution of cell.contributions) {
      if (contribution.project_line_id) {
        cellByLine.set(contribution.project_line_id, key);
        locationByLine.set(
          contribution.project_line_id,
          contribution.fulfilment_location ?? null,
        );
      }
      const pair = `${contribution.so_number} ${contribution.item_code}`;
      if (!cellByOrderItem.has(pair)) cellByOrderItem.set(pair, key);
    }
  }

  for (const order of batch.orders ?? []) {
    for (const row of order.rows ?? []) {
      const proposal = (row.proposal ?? null) as BoardContribution | null;
      const lineId = proposal?.project_line_id ?? null;
      const pair = `${order.so_number} ${row.item_code}`;
      const key =
        (lineId ? cellByLine.get(lineId) : undefined) ?? cellByOrderItem.get(pair) ?? null;
      if (!key) continue;
      const annotation = annotationOf(
        row,
        order.so_number,
        lineId ? locationByLine.get(lineId) ?? null : null,
      );
      const held = out.get(key);
      if (held) held.push(annotation);
      else out.set(key, [annotation]);
    }
  }
  return out;
}

/**
 * The decision every changed line arrives PRE-MARKED with (AC-P3-3).
 *
 * A row whose reaction leaves the line's own supply alone is approved as it stands; a row
 * carrying a fresh proposal is approved against that proposal, which is exactly what the
 * board's own Approve does to an undecided cell. Nothing is written: this seeds the board's
 * DRAFT, and Confirm is still the only write.
 */
export function preMarkedKeys(
  batch: Pick<PlanningChangeBatch, 'orders'> | null | undefined,
  contributions: BoardContribution[],
): string[] {
  if (!batch) return [];
  const changedLineIds = new Set<string>();
  for (const order of batch.orders ?? []) {
    for (const row of order.rows ?? []) {
      const proposal = (row.proposal ?? null) as BoardContribution | null;
      const lineId = row.project_line_id ?? proposal?.project_line_id ?? null;
      if (lineId) changedLineIds.add(lineId);
    }
  }
  return contributions
    .filter(
      (contribution) =>
        contribution.project_line_id !== null &&
        contribution.project_line_id !== undefined &&
        changedLineIds.has(contribution.project_line_id) &&
        !contribution.unplannable,
    )
    .map((contribution) => contribution.key);
}
