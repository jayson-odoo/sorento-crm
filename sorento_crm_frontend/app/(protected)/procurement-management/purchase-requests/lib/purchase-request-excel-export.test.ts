import { describe, it, expect, vi, beforeEach } from 'vitest';

import type { PurchaseRequest } from '../types/purchaseRequest.types';

// Capture the array-of-arrays handed to aoa_to_sheet so we can assert on the
// exact rows the export builds, without producing a real .xlsx download.
const captured: { aoa: (string | number)[][] | null } = { aoa: null };

vi.mock('xlsx', () => ({
  utils: {
    aoa_to_sheet: (aoa: (string | number)[][]) => {
      captured.aoa = aoa;
      return {} as unknown;
    },
    book_new: () => ({}) as unknown,
    book_append_sheet: () => undefined,
  },
  writeFile: () => undefined,
}));

import {
  exportSponsorshipFormToExcel,
  exportPurchaseRequestToExcel,
} from './purchase-request-excel-export';

function makeRequest(overrides: Partial<PurchaseRequest> = {}): PurchaseRequest {
  return {
    id: 'r1',
    request_number: 'PSSF26-0326',
    request_type: 'sponsorship_form',
    customer_name: 'BEDI Development Sdn Bhd',
    lines: [
      {
        id: 'l1',
        item_code: 'SRTUB6203',
        quantity: 2,
        unit_price: 60,
        total: 120,
        remark: 'Ceramic waste — urgent',
      },
    ],
    ...overrides,
  } as unknown as PurchaseRequest;
}

describe('exportSponsorshipFormToExcel', () => {
  beforeEach(() => {
    captured.aoa = null;
  });

  it('includes a Remark column in the line-items header', async () => {
    await exportSponsorshipFormToExcel(makeRequest());
    const header = captured.aoa!.find((r) => r[0] === 'NO.');
    expect(header).toEqual(['NO.', 'Item Code', 'Qty', 'U/P', 'Total', 'Remark']);
  });

  it('writes each line-item remark into the last column', async () => {
    await exportSponsorshipFormToExcel(makeRequest());
    const row = captured.aoa!.find((r) => r[0] === 1);
    expect(row?.[row.length - 1]).toBe('Ceramic waste — urgent');
  });

  it('keeps the Grand Total row aligned under Total (Remark cell blank)', async () => {
    await exportSponsorshipFormToExcel(makeRequest());
    const gt = captured.aoa!.find((r) => r.includes('Grand Total:'));
    expect(gt).toEqual(['', '', '', 'Grand Total:', '120.00', '']);
  });

  it('renders a blank remark when the line has none', async () => {
    await exportSponsorshipFormToExcel(
      makeRequest({
        lines: [
          { id: 'l1', item_code: 'X', quantity: 1, unit_price: 10, total: 10 },
        ] as unknown as PurchaseRequest['lines'],
      }),
    );
    const row = captured.aoa!.find((r) => r[0] === 1);
    expect(row?.[row.length - 1]).toBe('');
  });
});

describe('exportPurchaseRequestToExcel (unchanged — regression guard)', () => {
  beforeEach(() => {
    captured.aoa = null;
  });

  it('still has its Remark column', async () => {
    await exportPurchaseRequestToExcel(
      makeRequest({ request_type: 'purchase_request' }),
    );
    const header = captured.aoa!.find((r) => r[0] === '#');
    expect(header).toEqual(['#', 'Item Code', 'Qty', 'Remark']);
  });
});
