/**
 * QUOTE-AUTOSAVE review B2: a History entry carries every scope's stored lines (`record_lines`);
 * Restore stages them exactly the way the lines editor seeds a scope, and Save then writes them.
 */
import { describe, expect, it, vi } from 'vitest';

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }));

import { stagedFromRecordLines } from './QuotationFormClient';
import type { QuotationFormState } from '../../../_shared/services/quotationDocumentService';
import type { QuotationLine } from '../../../_shared/types/project.types';

function line(overrides: Partial<QuotationLine>): QuotationLine {
  return {
    id: 'l1',
    sort_order: 0,
    product_id: 'p9',
    description: 'Counter basin',
    quantity: '4',
    unit_price: '100.00',
    ...overrides,
  } as QuotationLine;
}

describe('stagedFromRecordLines', () => {
  it('stages a restored scope in sort order, every line marked as changed so Save sends it', () => {
    const state = {
      v: 1,
      header: {},
      letter: {},
      scopes: [{ key: 'q1', id: 'q1', scope_label: 'Townhouse', series_id: '' }],
      staged: {},
      removedIds: [],
      total: '0',
      record_lines: {
        q1: {
          versionId: 'v7',
          matrix_columns: [],
          lines: [line({ id: 'l2', sort_order: 1, unit_price: '200.00' }), line({ id: 'l1' })],
        },
      },
    } as QuotationFormState;

    const staged = stagedFromRecordLines(state);
    expect(staged.q1.versionId).toBe('v7');
    expect(staged.q1.seeded).toEqual([]);
    expect(staged.q1.lines.map((l) => [l.id, l.draft.unit_price])).toEqual([
      ['l1', '100.00'],
      ['l2', '200.00'],
    ]);
    expect(staged.q1.lines[0].line?.id).toBe('l1');
  });

  it('a line the record no longer holds comes back as a new line (no id, no stored line)', () => {
    const state = {
      v: 1,
      header: {},
      letter: {},
      scopes: [],
      staged: {},
      removedIds: [],
      total: '0',
      record_lines: { q1: { versionId: 'v7', lines: [line({ id: null as unknown as string })] } },
    } as QuotationFormState;
    const [restored] = stagedFromRecordLines(state).q1.lines;
    expect(restored.id).toBeNull();
    expect(restored.line).toBeNull();
    expect(restored.key).toBe('restored:q1:0');
    expect(restored.draft.description).toBe('Counter basin');
  });
});
