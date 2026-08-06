/**
 * PIC reaches the Excel export, for both form types.
 *
 * Background: there was nowhere to record the person receiving the delivery, so
 * staff typed them onto the end of the delivery address
 * ("... Pulau Pinang Contact: Hanson (012-403 9611)"). PIC is now its own field,
 * and it has to survive into every export or people will go straight back to
 * putting it in the address.
 *
 * The export builds an array-of-rows and hands it to the sheet writer, so the
 * assertion is on the rows: PIC present, and positioned directly under Customer
 * Name so the printed order matches the form.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const addedSheets: { name: string; rows: unknown[][] }[] = [];

vi.mock('xlsx', () => {
  const utils = {
    book_new: () => ({}),
    aoa_to_sheet: (rows: unknown[][]) => ({ __rows: rows }),
    book_append_sheet: (_wb: unknown, ws: { __rows: unknown[][] }, name: string) => {
      addedSheets.push({ name, rows: ws.__rows });
    },
    encode_cell: () => 'A1',
  };
  return { utils, writeFile: vi.fn(), write: vi.fn(() => new Uint8Array()), default: { utils } };
});

import { exportPurchaseRequestOrSponsorshipToExcel } from './purchase-request-excel-export';

function request(over: Record<string, unknown> = {}) {
  return {
    id: 'pr-1',
    request_type: 'purchase_request',
    request_number: 'PR26-0332',
    customer_name: 'KEE LIN TRADING SDN BHD',
    pic: 'Hanson (012-403 9611)',
    delivery_address: '2, Lebuh Cecil, Ghaut, 10300 George Town',
    project_title: 'ECO SUMMIT',
    lines: [],
    ...over,
  } as never;
}

function flatRows() {
  return addedSheets.flatMap((s) => s.rows);
}

describe('PIC in the PR / SF Excel export', () => {
  beforeEach(() => {
    addedSheets.length = 0;
  });

  it.each([['purchase_request'], ['sponsorship_form']])(
    'writes the PIC row for %s',
    async (request_type) => {
      await exportPurchaseRequestOrSponsorshipToExcel(request({ request_type }));

      const pic = flatRows().find((r) => String(r?.[0]).startsWith('PIC'));
      expect(pic, 'no PIC row in the exported sheet').toBeTruthy();
      expect(String(pic?.[1])).toContain('Hanson');
    },
  );

  it('puts PIC directly under Customer Name, matching the form', async () => {
    await exportPurchaseRequestOrSponsorshipToExcel(request());

    const rows = flatRows();
    const customer = rows.findIndex((r) => String(r?.[0]).startsWith('Customer Name'));
    const pic = rows.findIndex((r) => String(r?.[0]).startsWith('PIC'));
    expect(customer).toBeGreaterThanOrEqual(0);
    expect(pic).toBe(customer + 1);
  });

  it('renders an empty PIC without printing "null"', async () => {
    await exportPurchaseRequestOrSponsorshipToExcel(request({ pic: null }));

    const pic = flatRows().find((r) => String(r?.[0]).startsWith('PIC'));
    expect(pic).toBeTruthy();
    expect(String(pic?.[1]).toLowerCase()).not.toContain('null');
  });
});
