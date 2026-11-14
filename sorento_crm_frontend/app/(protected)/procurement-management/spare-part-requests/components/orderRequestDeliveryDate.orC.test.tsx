/**
 * SPARE-PART-OR-B C, red-first (Phase 2). C5.1 relabel: "Needed by" reads "Delivery date" on
 * the OR screens: the OI page General card of an order request and the OR list column (the
 * form is SparePartRequestForm.orC.test.tsx). The API field `needed_by` is unchanged.
 * Contract: documentation/plans/purchasing/spare-part-or-c-14nov-acceptance-criteria.md.
 *
 * NAMED CONTRACT CHOICE: the list column is found by its `meta.headerTitle` on the list's
 * source (mounting the DataGrid list needs its whole query stack; the title is what is pinned).
 */
import React from 'react';
import fs from 'node:fs';
import path from 'node:path';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { OrderInquiryGeneralTab } from '@/app/(protected)/project-sales/order-inquiries/[id]/components/OrderInquiryGeneralTab';

afterEach(cleanup);

const SPARE = {
  id: 'oi-1',
  inquiry_no: 'OR-2611-0007',
  oi_no: 'OI-2611-0003',
  inquiry_type: 'spare_part_request',
  state: 'raised',
  status: 'open',
  so_number: null,
  sales_order_id: null,
  project_sales_order_id: null,
  currency: 'MYR',
  needed_by: '2026-12-15',
  default_location: 'BRW',
  reason: 'Van spares',
  requested_by: 'u-1',
  requested_by_name: 'Requester One',
  submitted_at: '2026-11-12T02:00:00',
  approved_at: '2026-11-13T03:00:00',
  approved_by: 'u-2',
  approved_by_name: 'Approver One',
  reject_reason: null,
  raise_history: [],
} as never;

describe('C5.1: the General card of an order request', () => {
  it('reads "Delivery date" with the header date, never "Needed by"', () => {
    render(<OrderInquiryGeneralTab header={SPARE} />);
    expect(screen.getByText('Delivery date')).toBeInTheDocument();
    expect(screen.getByText('15/12/2026')).toBeInTheDocument();
    expect(screen.queryByText(/Needed by/i)).toBeNull();
  });
});

describe('C5.1: the order request list column', () => {
  it('is titled "Delivery date", never "Needed by"', () => {
    const source = fs.readFileSync(
      path.resolve(path.dirname(new URL(import.meta.url).pathname), './SparePartRequestsList.tsx'),
      'utf8',
    );
    expect(source).not.toMatch(/Needed by/);
    expect(source).toMatch(/headerTitle: 'Delivery date'/);
  });
});
