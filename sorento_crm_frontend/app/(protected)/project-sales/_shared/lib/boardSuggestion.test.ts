/**
 * What the ladder is proposing for a cell, said as quantities by KIND OF SOURCE.
 *
 * The dialog used to open on a table of lines and a stock position, and the planner had to
 * read a source strip per line to work out what the whole cell was being asked to do. The
 * decision is the point of the screen, so it is a card: four fixed rows, always in the same
 * order, so "Buy" is in the same place whether it is 0 or 300.
 *
 * The four are not the ladder's rung names, because those are the engine's vocabulary and this
 * card is read by a person deciding: what the rungs actually DO is take stock from this line's
 * own site, take it from another location in the same ownership group, borrow it from outside
 * the group, or buy it. That mapping is pinned here.
 */
import { describe, expect, it } from 'vitest';
import { suggestionBreakdown } from './boardSuggestion';
import type { BoardCell, BoardContribution, BoardSource } from '../types/fulfilmentPlanning.types';

function source(over: Partial<BoardSource> = {}): BoardSource {
  return { kind: 'reserve', qty: '10', reason: 'because', ...over };
}

function line(over: Partial<BoardContribution> = {}): BoardContribution {
  return {
    key: 'so-1:10',
    sales_order_id: 'so-1',
    so_number: 'SO416191',
    line_no: 10,
    item_code: 'CB2805A-DIY',
    qty: '13',
    qty_outstanding: '13',
    fulfilment_location: 'BRW-BB',
    unplannable: false,
    rank_score: 0,
    rank_factors: [],
    sources: [],
    trail: [],
    item_flags: null,
    contested: false,
    covered: false,
    decision: null,
    ...over,
  };
}

function cell(contributions: BoardContribution[]): BoardCell {
  return {
    item_code: 'CB2805A-DIY',
    bucket_key: '2026-09-01',
    total_qty: '13',
    locations: [],
    contributions,
    unplannable_count: 0,
    contested_count: 0,
  };
}

/** The row for a label, by its label. */
function row(rows: ReturnType<typeof suggestionBreakdown>, label: string) {
  const found = rows.find((entry) => entry.label === label);
  if (!found) throw new Error(`no row labelled ${label}`);
  return found;
}

/** Is this label on the card at all? A row with no quantity is not. */
function has(rows: ReturnType<typeof suggestionBreakdown>, label: string) {
  return rows.some((entry) => entry.label === label);
}

describe('suggestionBreakdown', () => {
  it('states only the kinds with a quantity, keeping their fixed order', () => {
    // Reversed 25 August 2026, from "always all four, an empty one muted". Three of the four
    // read 0 on almost every real cell, so the card was three lines of nothing around the one
    // line that said what to do - and the reader had to find it each time. What the card is
    // for is the decision, so it shows the decision.
    const rows = suggestionBreakdown(
      cell([
        line({
          sources: [
            source({ kind: 'buy', rung: 'buy', qty: '3', location: null }),
            source({ kind: 'reserve', rung: 'pool', qty: '13', location: 'BRW' }),
          ],
        }),
      ]),
    );

    expect(rows.map((entry) => entry.label)).toEqual(['Buy', 'Use own location']);
  });

  it('says nothing at all for a cell the ladder proposes nothing for', () => {
    expect(suggestionBreakdown(cell([line()]))).toEqual([]);
  });

  it('reads a pool rung at the line own site as its own location', () => {
    // The captain's live cell: "Pool 13 at BRW" on a line fulfilled from BRW-BB. The pool is
    // named by SITE and the line by warehouse, so the two are compared on the site prefix.
    const rows = suggestionBreakdown(
      cell([
        line({
          sources: [source({ kind: 'reserve', rung: 'pool', qty: '13', location: 'BRW' })],
        }),
      ]),
    );

    expect(row(rows, 'Use own location').qty).toBe('13');
    expect(row(rows, 'Use own location').locations).toEqual(['BRW']);
    expect(has(rows, 'Use shared stock')).toBe(false);
  });

  it('reads a pool rung at ANOTHER site as shared stock', () => {
    const rows = suggestionBreakdown(
      cell([
        line({
          sources: [source({ kind: 'reserve', rung: 'pool', qty: '4', location: 'MWH' })],
        }),
      ]),
    );

    expect(row(rows, 'Use shared stock').qty).toBe('4');
    expect(row(rows, 'Use shared stock').locations).toEqual(['MWH']);
  });

  it('reads a group take, which is always a sibling location, as shared stock', () => {
    const rows = suggestionBreakdown(
      cell([
        line({
          sources: [
            source({ kind: 'reserve', rung: 'group_take', qty: '6', location: 'DC1-BB' }),
          ],
        }),
      ]),
    );

    expect(row(rows, 'Use shared stock').qty).toBe('6');
    expect(row(rows, 'Use shared stock').locations).toEqual(['DC1-BB']);
  });

  it('reads a group borrow AT the line own location as its own location', () => {
    // "the agent's other customers' stock there" - it is committed to another order, but it
    // is sitting in this line's own warehouse, and that is what the planner is deciding about.
    const rows = suggestionBreakdown(
      cell([
        line({
          sources: [
            source({ kind: 'borrow', rung: 'group_borrow', qty: '3', location: 'BRW-BB' }),
          ],
        }),
      ]),
    );

    expect(row(rows, 'Use own location').qty).toBe('3');
    expect(has(rows, 'Borrow other location')).toBe(false);
  });

  it('reads a cross-group borrow as borrowing another location, whatever its code', () => {
    const rows = suggestionBreakdown(
      cell([
        line({
          sources: [
            source({
              kind: 'borrow',
              rung: 'cross_group_borrow',
              qty: '9',
              location: 'BRW-HP',
            }),
          ],
        }),
      ]),
    );

    expect(row(rows, 'Borrow other location').qty).toBe('9');
    expect(row(rows, 'Borrow other location').locations).toEqual(['BRW-HP']);
    expect(has(rows, 'Use own location')).toBe(false);
  });

  it('reads a buy as a buy, and names no location because it is held nowhere yet', () => {
    const rows = suggestionBreakdown(
      cell([line({ sources: [source({ kind: 'buy', rung: 'buy', qty: '13', location: null })] })]),
    );

    expect(row(rows, 'Buy').qty).toBe('13');
    expect(row(rows, 'Buy').locations).toEqual([]);
  });

  it('sums across every line of the cell and lists each location once', () => {
    const rows = suggestionBreakdown(
      cell([
        line({
          key: 'a',
          sources: [source({ kind: 'reserve', rung: 'pool', qty: '5', location: 'BRW' })],
        }),
        line({
          key: 'b',
          sources: [
            source({ kind: 'reserve', rung: 'pool', qty: '8', location: 'BRW' }),
            source({ kind: 'reserve', rung: 'group_take', qty: '2', location: 'MWH-BB' }),
          ],
        }),
      ]),
    );

    expect(row(rows, 'Use own location').qty).toBe('13');
    expect(row(rows, 'Use own location').locations).toEqual(['BRW']);
    expect(row(rows, 'Use shared stock').qty).toBe('2');
  });

  it('carries incoming supply as its own row, and only when there is some', () => {
    // Not one of the captain's four, and never folded into them: the incoming quantity is
    // already bought and on its way, and adding it to "Buy" would propose buying it twice.
    const none = suggestionBreakdown(cell([line()]));
    expect(none.some((entry) => entry.label === 'Incoming supply')).toBe(false);

    const rows = suggestionBreakdown(
      cell([
        line({
          sources: [
            source({ kind: 'timely_spo', rung: 'incoming', qty: '7', location: 'BRW-BB' }),
          ],
        }),
      ]),
    );

    expect(row(rows, 'Incoming supply').qty).toBe('7');
    expect(rows[rows.length - 1].label).toBe('Incoming supply');
  });

  it('carries the engine own sentence when every source on the row gives the same one', () => {
    // The one that matters: a Buy for "nothing free anywhere" and a Buy for "beyond the lead
    // time window" are the same quantity for opposite reasons, and this card is where the
    // planner decides between them.
    const rows = suggestionBreakdown(
      cell([
        line({
          sources: [
            source({
              kind: 'buy',
              rung: 'buy',
              qty: '13',
              location: null,
              reason: 'Delivery date beyond the lead time window; stock kept for nearer orders',
            }),
          ],
        }),
      ]),
    );

    expect(row(rows, 'Buy').note).toBe(
      'Delivery date beyond the lead time window; stock kept for nearer orders',
    );
  });

  it('says nothing when the lines on a row disagree about why', () => {
    const rows = suggestionBreakdown(
      cell([
        line({ key: 'a', sources: [source({ kind: 'buy', qty: '5', reason: 'one reason' })] }),
        line({ key: 'b', sources: [source({ kind: 'buy', qty: '5', reason: 'another' })] }),
      ]),
    );

    expect(row(rows, 'Buy').qty).toBe('10');
    expect(row(rows, 'Buy').note).toBeUndefined();
  });

  it('says nothing can be sourced for a line whose order states no location', () => {
    // The ladder was never walked for it, so every one of the four is 0 and the card must not
    // imply a proposal that does not exist.
    const rows = suggestionBreakdown(
      cell([line({ unplannable: true, sources: [source({ kind: 'unplannable', qty: '13' })] })]),
    );

    expect(rows.every((entry) => entry.qty === '0')).toBe(true);
  });
});
