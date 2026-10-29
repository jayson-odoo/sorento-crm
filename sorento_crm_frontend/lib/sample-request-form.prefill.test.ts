/**
 * SAMPLE-FROM-QUOTE: the pure pre-fill rules both sample request forms share (UAC SFQ-20..25,
 * documentation/plans/project-sales/sample-from-quote-29oct-acceptance-criteria.md).
 */
import { describe, expect, it } from 'vitest';
import {
  EMPTY_FORM,
  blankLine,
  linesUntouched,
  payloadFromState,
  prefillFromQuotation,
  prefillNote,
  stateFromDetail,
  type FormState,
} from '@/lib/sample-request-form';
import type { SampleRequestDetail, SampleRequestQuotationPrefill } from '@/types/sampleRequest';

const PREFILL: SampleRequestQuotationPrefill = {
  documents: [
    { id: 'doc-1', document_no: 'Q-0001', issue_id: 'iss-2', issue_no: 2, label: 'Q-0001 (R2)' },
  ],
  document_id: 'doc-1',
  issue_id: 'iss-2',
  lines: [
    { product_id: 'p-1', product_code: 'BASIN-1', product_name: 'Basin', brand_name: 'B' },
    { product_id: 'p-2', product_code: 'TAP-2', product_name: 'Tap', brand_name: null },
  ],
  skipped: [
    { reason: 'no_product', description: 'Bespoke vanity top' },
    { reason: 'no_product', description: 'Site labour' },
    { reason: 'inactive', description: 'OLD-9' },
  ],
};

const form = (over: Partial<FormState> = {}): FormState => ({
  ...EMPTY_FORM,
  lines: [blankLine()],
  ...over,
});

describe('prefillFromQuotation (SFQ-20, SFQ-25)', () => {
  it('turns each quotation product into a row of qty 1 with no remark and records the source', () => {
    const next = prefillFromQuotation(PREFILL, 'note');
    expect(next.lines.map((l) => [l.product_id, l.label, l.qty, l.remark])).toEqual([
      ['p-1', 'BASIN-1 - Basin', '1', ''],
      ['p-2', 'TAP-2 - Tap', '1', ''],
    ]);
    expect(next.quotation_document_id).toBe('doc-1');
    expect(next.quotation_issue_id).toBe('iss-2');
  });

  it("'row' adds each free-text line as an empty-product row carrying its description", () => {
    const next = prefillFromQuotation(PREFILL, 'row');
    expect(next.lines.map((l) => [l.product_id, l.remark])).toEqual([
      ['p-1', ''],
      ['p-2', ''],
      ['', 'Bespoke vanity top'],
      ['', 'Site labour'],
    ]);
  });

  it('a quotation with nothing to pre-fill leaves one blank row and no source', () => {
    const next = prefillFromQuotation({ ...PREFILL, lines: [], skipped: [] }, 'note');
    expect(next.lines).toHaveLength(1);
    expect(next.lines[0].product_id).toBe('');
    expect(next.quotation_document_id).toBe('');
    expect(next.quotation_issue_id).toBe('');
  });
});

describe('linesUntouched (SFQ-20, SFQ-22)', () => {
  it('a form with only blank rows is untouched', () => {
    expect(linesUntouched(form())).toBe(true);
    expect(linesUntouched(form({ lines: [] }))).toBe(true);
  });

  it('pre-filled rows stay untouched until a row is deleted, added, or edited', () => {
    const filled = form(prefillFromQuotation(PREFILL, 'note'));
    expect(linesUntouched(filled)).toBe(true);
    expect(linesUntouched({ ...filled, lines: filled.lines.slice(1) })).toBe(false);
    expect(linesUntouched({ ...filled, lines: [...filled.lines, blankLine()] })).toBe(false);
    expect(
      linesUntouched({ ...filled, lines: [{ ...filled.lines[0], qty: '3' }, filled.lines[1]] }),
    ).toBe(false);
  });

  it('rows a person typed are touched', () => {
    expect(linesUntouched(form({ lines: [{ ...blankLine(), product_id: 'p-9', label: 'X' }] }))).toBe(
      false,
    );
  });
});

describe('prefillNote (SFQ-25)', () => {
  it("'note' counts free text and inactive lines", () => {
    expect(prefillNote(PREFILL, 'note')).toBe(
      '3 quotation lines were not added: 2 have no product, 1 product is inactive.',
    );
  });

  it("'row' counts only inactive products, since free text became rows", () => {
    expect(prefillNote(PREFILL, 'row')).toBe(
      '1 quotation line was not added: 1 product is inactive.',
    );
  });

  it('nothing skipped, no note', () => {
    expect(prefillNote({ ...PREFILL, skipped: [] }, 'note')).toBeNull();
  });
});

describe('the source travels with the request (SFQ-12)', () => {
  it('the payload carries the source, or nulls', () => {
    const filled = form(prefillFromQuotation(PREFILL, 'note'));
    expect(payloadFromState(filled)).toMatchObject({
      quotation_document_id: 'doc-1',
      quotation_issue_id: 'iss-2',
    });
    expect(payloadFromState(form())).toMatchObject({
      quotation_document_id: null,
      quotation_issue_id: null,
    });
  });

  it('a loaded draft keeps its source and is never treated as untouched pre-fill', () => {
    const detail = {
      project_id: 'proj-1',
      quotation_document_id: 'doc-1',
      quotation_issue_id: null,
      lines: [
        {
          id: 'l1',
          line_no: 1,
          product_id: 'p-1',
          product_code: 'BASIN-1',
          product_name: 'Basin',
          brand_name: null,
          product_active: true,
          qty: 1,
          remark: null,
        },
      ],
    } as unknown as SampleRequestDetail;
    const loaded = stateFromDetail(detail);
    expect(loaded.quotation_document_id).toBe('doc-1');
    expect(loaded.quotation_issue_id).toBe('');
    expect(linesUntouched(loaded)).toBe(false);
  });
});
