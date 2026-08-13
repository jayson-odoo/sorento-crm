/**
 * Exporting ONE stored revision of a stock inquiry (round 6, 6.3).
 *
 * The two things worth pinning: the sheet shows the SUPERSEDED values (never
 * today's), and it says which version it is. A revision sheet that quietly
 * printed the live purchasing reply under a historical heading would be read as
 * fact.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import type { FormRevisionEntry } from '@/components/common/RevisionTimeline';
import type { StockInquiryDetail } from '../types/stockInquiry.types';
import { revisionEntryToStockInquiry } from './revisionEntryToStockInquiry';
import {
  buildFormRows,
  buildStockInquiryRevisionRows,
  buildStockInquiryRevisionSheets,
  exportStockInquiryRevisionToExcel,
} from './exportStockInquiryToExcel';

function live(overrides: Partial<StockInquiryDetail> = {}): StockInquiryDetail {
  return {
    id: 'si-1',
    inquiry_number: 'SI-26-0184',
    salesperson: 'Alice Tan',
    product_code: 'PRD-9',
    item_description: 'Latest description',
    project_customer: 'Acme',
    project_name: 'Tower B',
    quantity: '20',
    delivery_date: 'ASAP',
    remark: 'Latest remark',
    additional_remark: null,
    purchasing_response: 'Stock arrives 20 Aug',
    status: 'responded',
    rejection_reason: 'Rejected earlier',
    reopen_reason: 'Reopened earlier',
    void_reason: null,
    last_responded_by: 'user-1',
    last_responded_by_name: 'Bob Lim',
    last_responded_at: '2026-08-13T02:00:00',
    revision_no: 2,
    created_at: '2026-07-01T02:00:00' as unknown as Date,
    updated_at: '2026-08-13T02:00:00' as unknown as Date,
    ...overrides,
  } as StockInquiryDetail;
}

function entry(overrides: Partial<FormRevisionEntry> = {}): FormRevisionEntry {
  return {
    id: 'rev-1',
    version_no: 1,
    revision_no: 1,
    kind: 'revision',
    label: 'Revision 1',
    reason: 'Quantity was wrong',
    submitted_at: '2026-08-12T02:00:00',
    submitted_by: 'Alice Tan',
    snapshot: {
      inquiry_number: 'SI-26-0184',
      status: 'pending_purchasing',
      salesperson: 'Alice Tan',
      product_code: 'PRD-9',
      item_description: 'Superseded description',
      project_customer: 'Acme',
      project_name: 'Tower B',
      quantity: '10',
      delivery_date: 'ASAP',
      remark: 'Superseded remark',
      additional_remark: null,
    },
    attachments: [],
    changes: [],
    ...overrides,
  };
}

describe('revisionEntryToStockInquiry', () => {
  it('lets the snapshot win over the live record', () => {
    const adapted = revisionEntryToStockInquiry(entry(), live());
    expect(adapted.quantity).toBe('10');
    expect(adapted.item_description).toBe('Superseded description');
    expect(adapted.remark).toBe('Superseded remark');
  });

  it('blanks the live-only fields instead of reporting today under a historical heading', () => {
    const adapted = revisionEntryToStockInquiry(entry(), live());
    expect(adapted.purchasing_response).toBeNull();
    expect(adapted.last_responded_by).toBeNull();
    expect(adapted.last_responded_by_name).toBeNull();
    expect(adapted.last_responded_at).toBeNull();
    expect(adapted.rejection_reason).toBeNull();
    expect(adapted.reopen_reason).toBeNull();
    expect(adapted.void_reason).toBeNull();
    // Stored, but it is the superseded version's status - the PDF never prints
    // it either.
    expect(adapted.status).toBeNull();
  });

  it('keeps identity from the live record and suffixes the document number', () => {
    const adapted = revisionEntryToStockInquiry(entry({ revision_no: 2 }), live());
    expect(adapted.id).toBe('si-1');
    expect(adapted.inquiry_number).toBe('SI-26-0184-R2');
  });

  it('renders the original submission bare, with no -R0', () => {
    const adapted = revisionEntryToStockInquiry(
      entry({ kind: 'original', revision_no: 0, label: 'Original' }),
      live(),
    );
    expect(adapted.inquiry_number).toBe('SI-26-0184');
  });

  it('dates the form the day THIS version was submitted', () => {
    const adapted = revisionEntryToStockInquiry(entry(), live());
    expect(adapted.created_at).toBe('2026-08-12T02:00:00');
  });
});

describe('buildStockInquiryRevisionRows', () => {
  function valueOf(rows: (string | number)[][], label: string) {
    return rows.find((row) => row[0] === label)?.[1];
  }

  it('feeds the existing form builder the superseded values', () => {
    const rows = buildStockInquiryRevisionRows(entry(), live());
    expect(valueOf(rows, 'QTY:')).toBe('10');
    expect(valueOf(rows, 'ITEM DESCRIPTION:')).toBe('Superseded description');
    expect(valueOf(rows, 'STOCK INQUIRY NUMBER:')).toBe('SI-26-0184-R1');
    expect(valueOf(rows, 'DATE:')).toBe('12/08/2026');
    expect(valueOf(rows, 'COMMENT / REPLY BY PURCHASING:')).toBe('');
  });

  it('says which version the sheet is', () => {
    const rows = buildStockInquiryRevisionRows(entry(), live());
    expect(valueOf(rows, 'REVISION:')).toBe('Revision 1');
    expect(valueOf(rows, 'REASON:')).toBe('Quantity was wrong');
    expect(valueOf(rows, 'SUBMITTED:')).toBe('12/08/2026 by Alice Tan');
  });

  it('keeps the document title and the form layout it has always had', () => {
    const currentRows = buildFormRows(live());
    const rows = buildStockInquiryRevisionRows(entry(), live());
    expect(rows[0]).toEqual(['PRODUCT INQUIRY FORM']);
    expect(rows.map((row) => row[0]).filter(Boolean)).toEqual(
      expect.arrayContaining(currentRows.map((row) => row[0]).filter(Boolean)),
    );
  });
});

/**
 * The include-revisions workbook (round 6, 6.4; corrected round 7).
 *
 * The newest lineage entry gets NO sheet: it is the version sheet 1 already
 * shows, so a sheet for it repeated the current form with the office fields
 * blanked - the "double print" the user reported on the PDF, in a workbook.
 */
describe('buildStockInquiryRevisionSheets', () => {
  function valueOf(rows: (string | number)[][], label: string) {
    return rows.find((row) => row[0] === label)?.[1];
  }

  const original = () =>
    entry({ id: 'rev-0', version_no: 0, revision_no: 0, kind: 'original', label: 'Original', reason: null });
  const newest = () =>
    entry({
      id: 'rev-2',
      version_no: 2,
      revision_no: 2,
      label: 'Revision 2',
      reason: 'Model changed',
      snapshot: { ...(entry().snapshot as Record<string, unknown>), item_description: 'Latest description' },
    });

  it('is the current form, then every EARLIER version newest first', () => {
    const sheets = buildStockInquiryRevisionSheets(live(), [original(), entry(), newest()]);
    expect(sheets.map((sheet) => sheet.name)).toEqual([
      'Stock Inquiry',
      'Revision 1',
      'Original',
    ]);
  });

  it('carries the newest version onto sheet 1 instead of giving it a sheet', () => {
    const sheets = buildStockInquiryRevisionSheets(live(), [original(), entry(), newest()]);
    expect(valueOf(sheets[0]!.rows, 'REVISION:')).toBe('Revision 2');
    expect(valueOf(sheets[0]!.rows, 'REASON:')).toBe('Model changed');
    expect(valueOf(sheets[0]!.rows, 'SUBMITTED:')).toBe('12/08/2026 by Alice Tan');
    // ...and the form itself is untouched: sheet 1 is still the live record.
    expect(valueOf(sheets[0]!.rows, 'ITEM DESCRIPTION:')).toBe('Latest description');
    expect(valueOf(sheets[0]!.rows, 'COMMENT / REPLY BY PURCHASING:')).toBe('Stock arrives 20 Aug');
    // Exactly one sheet holds the newest version's values.
    const carrying = sheets.filter(
      (sheet) => valueOf(sheet.rows, 'ITEM DESCRIPTION:') === 'Latest description',
    );
    expect(carrying).toHaveLength(1);
  });

  it('is just the current sheet when the lineage is only the original', () => {
    const sheets = buildStockInquiryRevisionSheets(live(), [original()]);
    expect(sheets.map((sheet) => sheet.name)).toEqual(['Stock Inquiry']);
    // Nothing to say about a version, so the block does not appear at all.
    expect(valueOf(sheets[0]!.rows, 'REVISION:')).toBeUndefined();
    expect(sheets[0]!.rows).toEqual(buildFormRows(live()));
  });

  it('treats a resubmission lineage the same, though it is still at revision 0', () => {
    const resubmitted = entry({
      id: 'rev-r',
      version_no: 1,
      revision_no: 0,
      kind: 'resubmission',
      label: 'Resubmitted',
    });
    const sheets = buildStockInquiryRevisionSheets(live(), [original(), resubmitted]);
    expect(sheets.map((sheet) => sheet.name)).toEqual(['Stock Inquiry', 'Original']);
    expect(valueOf(sheets[0]!.rows, 'REVISION:')).toBe('Resubmitted');
  });
});

describe('exportStockInquiryRevisionToExcel', () => {
  const clicks: string[] = [];
  let clickSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    clicks.length = 0;
    URL.createObjectURL = vi.fn(() => 'blob:test');
    URL.revokeObjectURL = vi.fn();
    clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(function (this: HTMLAnchorElement) {
        clicks.push(this.download);
      });
  });

  afterEach(() => {
    clickSpy.mockRestore();
  });

  it('names the file after THAT version, the same way the PDF of it is named', async () => {
    await exportStockInquiryRevisionToExcel(entry({ revision_no: 1 }), live());
    expect(clicks).toEqual(['Stock_Inquiry_SI-26-0184-R1-as-submitted.xlsx']);
  });

  it('never collides with the live record export of the same revision', async () => {
    // The live record is at R2; its own export is `Stock_Inquiry_SI-26-0184-R2`
    // and carries office fields this snapshot cannot.
    await exportStockInquiryRevisionToExcel(entry({ revision_no: 2 }), live());
    expect(clicks).toEqual(['Stock_Inquiry_SI-26-0184-R2-as-submitted.xlsx']);
  });

  it('keeps version 0 apart from the current form of an unrevised record', async () => {
    await exportStockInquiryRevisionToExcel(
      entry({ kind: 'original', revision_no: 0, version_no: 0 }),
      live(),
    );
    expect(clicks).toEqual(['Stock_Inquiry_SI-26-0184-original.xlsx']);
  });
});
