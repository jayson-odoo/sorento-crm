/**
 * Exporting a purchase request / sponsorship form revision (round 6, 6.3/6.4).
 *
 * Same contract the stock inquiry export is held to: the sheet shows the
 * SUPERSEDED values, says which version it is, and the multi-sheet workbook
 * leaves sheet 1 exactly as it has always been.
 *
 * SheetJS is faked so the assertions are about the rows and the sheet names -
 * the real `writeFile` would put a workbook on disk, which proves nothing.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const writeFile = vi.fn();
const appended: { name: string; aoa: (string | number)[][] }[] = [];

vi.mock('xlsx', () => ({
  utils: {
    aoa_to_sheet: (aoa: (string | number)[][]) => ({ aoa }),
    book_new: () => ({ SheetNames: [] as string[] }),
    book_append_sheet: (
      _wb: unknown,
      ws: { aoa: (string | number)[][] },
      name: string,
    ) => {
      appended.push({ name, aoa: ws.aoa });
    },
  },
  writeFile: (...args: unknown[]) => writeFile(...args),
}));

import type { FormRevisionEntry } from '@/components/common/RevisionTimeline';
import type { PurchaseRequest } from '../types/purchaseRequest.types';
import { revisionEntryToPurchaseRequest } from './revisionEntryToPurchaseRequest';
import {
  buildPurchaseRequestAoa,
  buildPurchaseRequestRevisionAoa,
  createSalesTypeLabelResolver,
  exportPurchaseRequestOrSponsorshipRevisionToExcel,
  exportPurchaseRequestOrSponsorshipWithRevisionsToExcel,
} from './purchase-request-excel-export';

function live(overrides: Partial<PurchaseRequest> = {}): PurchaseRequest {
  return {
    id: 'pr-1',
    request_type: 'purchase_request',
    request_number: 'PR-26-0007',
    customer_name: 'Acme Holdings',
    pic: 'Jane (012-3456789)',
    project_title: 'Tower B',
    purpose: 'Latest purpose',
    sales_type: 'cash_sales',
    expected_delivery_date: '2026-09-01',
    expected_po_date: '2026-08-20',
    expected_po_date_text: 'Awaiting client',
    requested_by: 'Alice Tan',
    submitted_at: '2026-07-01T02:00:00',
    status: 'pending_approval',
    approval_status: 'approved',
    approved_by: 'Bob Lim',
    approved_at: '2026-08-10T02:00:00',
    approval_comments: 'Approved on the old version',
    approval_signature_ref: 'sig-1',
    void_reason: null,
    revision_no: 2,
    lines: [{ id: 'l-1', purchase_request_id: 'pr-1', item_code: 'LIVE-1', quantity: 5, remark: 'live' }],
    ...overrides,
  } as PurchaseRequest;
}

function entry(overrides: Partial<FormRevisionEntry> = {}): FormRevisionEntry {
  return {
    id: 'rev-1',
    version_no: 1,
    revision_no: 1,
    kind: 'revision',
    label: 'Revision 1',
    reason: 'Wrong item',
    submitted_at: '2026-08-12T02:00:00',
    submitted_by: 'Alice Tan',
    snapshot: {
      request_number: 'PR-26-0007',
      status: 'pending_project_sales',
      customer_name: 'Acme Holdings',
      pic: 'Jane (012-3456789)',
      project_title: 'Tower B',
      purpose: 'Superseded purpose',
      sales_type: 'project',
      expected_delivery_date: '2026-09-01',
      expected_po_date: '2026-08-20',
      requested_by: 'Alice Tan',
      products: [
        { item_code: 'OLD-1', quantity: '3', unit_price: '10.00', total: '30.00', remark: 'old' },
      ],
    },
    attachments: [],
    changes: [],
    ...overrides,
  };
}

function valueOf(aoa: (string | number)[][], label: string) {
  return aoa.find((row) => row[0] === label)?.[1];
}

beforeEach(() => {
  writeFile.mockClear();
  appended.length = 0;
});

describe('revisionEntryToPurchaseRequest', () => {
  it('lets the snapshot win over the live record', () => {
    const adapted = revisionEntryToPurchaseRequest(entry(), live());
    expect(adapted.purpose).toBe('Superseded purpose');
    expect(adapted.sales_type).toBe('project');
  });

  it('maps snapshot products onto lines, in the stored order', () => {
    const adapted = revisionEntryToPurchaseRequest(
      entry({
        snapshot: {
          ...(entry().snapshot as Record<string, unknown>),
          products: [
            { item_code: 'OLD-1', quantity: '3', unit_price: '10.00', total: '30.00', remark: 'a' },
            { item_code: 'OLD-2', quantity: '1', unit_price: '2.50', total: '2.50', remark: 'b' },
          ],
        },
      }),
      live(),
    );
    expect(adapted.lines?.map((line) => line.item_code)).toEqual(['OLD-1', 'OLD-2']);
    expect(adapted.lines?.[0]?.quantity).toBe(3);
    expect(adapted.lines?.[1]?.total).toBe(2.5);
    expect(adapted.lines?.[1]?.sort_order).toBe(1);
  });

  it('blanks the live-only fields instead of reporting today under a historical heading', () => {
    const adapted = revisionEntryToPurchaseRequest(entry(), live());
    expect(adapted.approved_by).toBeNull();
    expect(adapted.approved_at).toBeNull();
    expect(adapted.approval_status).toBeNull();
    expect(adapted.approval_comments).toBeNull();
    expect(adapted.approval_signature_ref).toBeNull();
    expect(adapted.expected_po_date_text).toBeNull();
    expect(adapted.status).toBeNull();
  });

  it('keeps identity from the live record and carries the version number', () => {
    const adapted = revisionEntryToPurchaseRequest(entry(), live());
    expect(adapted.id).toBe('pr-1');
    expect(adapted.request_type).toBe('purchase_request');
    // Bare + `revision_no`: the document builders derive `-R1` themselves, so a
    // pre-suffixed value would print `-R1-R1`.
    expect(adapted.request_number).toBe('PR-26-0007');
    expect(adapted.revision_no).toBe(1);
  });

  it('dates the document the day THIS version was submitted', () => {
    const adapted = revisionEntryToPurchaseRequest(entry(), live());
    expect(adapted.submitted_at).toBe('2026-08-12T02:00:00');
  });
});

describe('buildPurchaseRequestRevisionAoa', () => {
  it('feeds the existing document builder the superseded values', () => {
    const aoa = buildPurchaseRequestRevisionAoa(entry(), live(), 'Project');
    expect(valueOf(aoa, 'Purpose:')).toBe('Superseded purpose');
    expect(valueOf(aoa, 'Sales Type:')).toBe('Project');
    expect(valueOf(aoa, 'Approved by:')).toBe('');
    expect(valueOf(aoa, 'Purchase request number:')).toBe('PR-26-0007-R1');
    // The snapshot's item, not the live one.
    expect(aoa.some((row) => row[1] === 'OLD-1')).toBe(true);
    expect(aoa.some((row) => row[1] === 'LIVE-1')).toBe(false);
  });

  it('says which version the sheet is, under the document title', () => {
    const aoa = buildPurchaseRequestRevisionAoa(entry(), live());
    expect(aoa[0]).toEqual(['Purchase Request']);
    expect(valueOf(aoa, 'Revision:')).toBe('Revision 1');
    expect(valueOf(aoa, 'Reason:')).toBe('Wrong item');
    expect(valueOf(aoa, 'Submitted:')).toBe('12/08/2026 by Alice Tan');
  });

  it('keeps the sponsorship letterhead above its own revision block', () => {
    const sf = live({ request_type: 'sponsorship_form' });
    const aoa = buildPurchaseRequestRevisionAoa(entry(), sf);
    expect(aoa[0]?.[0]).toBe('SORENTO SDN BHD');
    expect(aoa[4]).toEqual(['Project Sales Sponsorship Form']);
    expect(valueOf(aoa, 'Revision:')).toBe('Revision 1');
  });
});

describe('exportPurchaseRequestOrSponsorshipRevisionToExcel', () => {
  it('names the file after THAT version, the same way the PDF of it is named', async () => {
    await exportPurchaseRequestOrSponsorshipRevisionToExcel(entry({ revision_no: 1 }), live());
    expect(writeFile).toHaveBeenCalledWith(
      expect.anything(),
      'Purchase_Request_PR-26-0007-R1-as-submitted.xlsx',
    );
  });

  it('never collides with the live record export of the same revision', async () => {
    // The live record is at R2; its own export is `Purchase_Request_PR-26-0007-R2`
    // and carries the approval block this snapshot deliberately blanks.
    await exportPurchaseRequestOrSponsorshipRevisionToExcel(entry({ revision_no: 2 }), live());
    expect(writeFile).toHaveBeenCalledWith(
      expect.anything(),
      'Purchase_Request_PR-26-0007-R2-as-submitted.xlsx',
    );
  });

  it('keeps version 0 apart from the current form of an unrevised record', async () => {
    await exportPurchaseRequestOrSponsorshipRevisionToExcel(
      entry({ kind: 'original', revision_no: 0, version_no: 0 }),
      live(),
    );
    expect(writeFile).toHaveBeenCalledWith(
      expect.anything(),
      'Purchase_Request_PR-26-0007-original.xlsx',
    );
  });
});

describe('exportPurchaseRequestOrSponsorshipWithRevisionsToExcel', () => {
  const original = () =>
    ({
      ...entry(),
      id: 'rev-0',
      version_no: 0,
      revision_no: 0,
      kind: 'original',
      label: 'Original',
      reason: null,
    }) as FormRevisionEntry;

  const newest = () =>
    ({
      ...entry(),
      id: 'rev-2',
      version_no: 2,
      revision_no: 2,
      label: 'Revision 2',
      reason: 'Model changed',
    }) as FormRevisionEntry;

  it('puts the current form first, then every EARLIER version newest first', async () => {
    // Round 7: the newest entry ("Revision 2") is the version sheet 1 shows, so
    // it gets no sheet of its own - printing both was the same form twice.
    await exportPurchaseRequestOrSponsorshipWithRevisionsToExcel(live(), [
      original(),
      entry(),
      newest(),
    ]);
    expect(appended.map((sheet) => sheet.name)).toEqual([
      'Purchase Request',
      'Revision 1',
      'Original',
    ]);
    expect(writeFile).toHaveBeenCalledWith(expect.anything(), 'Purchase_Request_PR-26-0007-R2.xlsx');
  });

  it('carries the newest version onto sheet 1 instead of giving it a sheet', async () => {
    await exportPurchaseRequestOrSponsorshipWithRevisionsToExcel(live(), [original(), newest()]);
    expect(valueOf(appended[0]!.aoa, 'Revision:')).toBe('Revision 2');
    expect(valueOf(appended[0]!.aoa, 'Reason:')).toBe('Model changed');
    expect(valueOf(appended[0]!.aoa, 'Submitted:')).toBe('12/08/2026 by Alice Tan');
    // The form itself is untouched - sheet 1 is still the live record, approval
    // block and all.
    expect(valueOf(appended[0]!.aoa, 'Purpose:')).toBe('Latest purpose');
    expect(valueOf(appended[0]!.aoa, 'Approved by:')).toBe('Bob Lim');
  });

  it('is silently just the form when there is no lineage yet', async () => {
    await exportPurchaseRequestOrSponsorshipWithRevisionsToExcel(live(), [original()]);
    expect(appended.map((sheet) => sheet.name)).toEqual(['Purchase Request']);
    // Nothing to say about a version, so sheet 1 is byte-for-byte the export this
    // page has always produced.
    expect(appended[0]?.aoa).toEqual(buildPurchaseRequestAoa(live()));
  });

  it('treats a resubmission lineage the same, though it is still at revision 0', async () => {
    const resubmitted = {
      ...entry(),
      id: 'rev-r',
      version_no: 1,
      revision_no: 0,
      kind: 'resubmission',
      label: 'Resubmitted',
    } as FormRevisionEntry;
    await exportPurchaseRequestOrSponsorshipWithRevisionsToExcel(live(), [
      original(),
      resubmitted,
    ]);
    expect(appended.map((sheet) => sheet.name)).toEqual(['Purchase Request', 'Original']);
    expect(valueOf(appended[0]!.aoa, 'Revision:')).toBe('Resubmitted');
  });

  it('reads each version through its OWN sales type label', async () => {
    const resolve = createSalesTypeLabelResolver([
      { value: 'cash_sales', label: 'Cash Sales' },
      { value: 'project', label: 'Project' },
    ]);
    await exportPurchaseRequestOrSponsorshipWithRevisionsToExcel(
      live(),
      [entry(), newest()],
      resolve,
    );
    expect(valueOf(appended[0]!.aoa, 'Sales Type:')).toBe('Cash Sales');
    expect(valueOf(appended[1]!.aoa, 'Sales Type:')).toBe('Project');
  });
});
