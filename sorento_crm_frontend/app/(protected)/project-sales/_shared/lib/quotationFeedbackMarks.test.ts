/**
 * PS-QUOTE-MATRIX fix round 1: a note names an ISSUED line; a revise copies lines under new ids,
 * so the draft is matched by product (or set) and occurrence in sort order. Values invented.
 */
import { describe, expect, it } from 'vitest';
import type { QuotationFeedbackRow } from '../types/project.types';
import { carryFeedback } from './quotationFeedbackMarks';

function note(overrides: Partial<QuotationFeedbackRow>): QuotationFeedbackRow {
  return {
    id: 'f1',
    line_id: 'L1',
    scope_label: 'UNIT',
    line_description: null,
    cell_key: null,
    cell_label: null,
    kind: 'note',
    value_from: null,
    value_to: null,
    model: null,
    note: 'Hi',
    handled_at: null,
    handled_by_name: null,
    ...overrides,
  };
}

const ISSUED = [
  { id: 'L1', product_id: 'p-sink', product_set_id: null, sort_order: 0 },
  { id: 'L2', product_id: 'p-valve', product_set_id: null, sort_order: 1 },
  { id: 'L3', product_id: 'p-valve', product_set_id: null, sort_order: 2 },
  { id: 'L4', product_id: null, product_set_id: 's-wc', sort_order: 3 },
];
// The draft: copied with new ids, one line added on top (sort order shifts, occurrence does not).
const DRAFT = [
  { id: 'N0', product_id: 'p-new', product_set_id: null, sort_order: 0 },
  { id: 'L1b', product_id: 'p-sink', product_set_id: null, sort_order: 1 },
  { id: 'L2b', product_id: 'p-valve', product_set_id: null, sort_order: 2 },
  { id: 'L3b', product_id: 'p-valve', product_set_id: null, sort_order: 3 },
  { id: 'L4b', product_id: null, product_set_id: 's-wc', sort_order: 4 },
];

describe('carryFeedback', () => {
  it('issued line L1 -> its copy on the draft, cell key unchanged', () => {
    const carried = carryFeedback([note({ cell_key: 'c-kit' })], [ISSUED], DRAFT);
    expect(carried).toEqual([expect.objectContaining({ line_id: 'L1b', cell_key: 'c-kit' })]);
  });

  it('the same product twice goes to the same occurrence, and a set to its set', () => {
    const carried = carryFeedback(
      [note({ id: 'a', line_id: 'L3' }), note({ id: 'b', line_id: 'L2' }), note({ id: 'c', line_id: 'L4' })],
      [ISSUED],
      DRAFT,
    );
    expect(carried.map((row) => [row.id, row.line_id])).toEqual([
      ['a', 'L3b'],
      ['b', 'L2b'],
      ['c', 'L4b'],
    ]);
  });

  it('keeps a note on a line already on screen, and drops one with no copy', () => {
    expect(carryFeedback([note({ line_id: 'L1' })], [], ISSUED)[0].line_id).toBe('L1');
    const gone = carryFeedback([note({ line_id: 'L1' })], [ISSUED], DRAFT.filter((line) => line.id !== 'L1b'));
    expect(gone).toEqual([]);
    expect(carryFeedback([note({ line_id: 'elsewhere' })], [ISSUED], DRAFT)).toEqual([]);
  });
});
