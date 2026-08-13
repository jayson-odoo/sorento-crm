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
