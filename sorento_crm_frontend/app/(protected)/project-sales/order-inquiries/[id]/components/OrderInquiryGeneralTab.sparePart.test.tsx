/**
 * SPARE-PART-ORDER-REQUEST F2 (UAC P4, H1): the OI page's General tab, for an inquiry of
 * type `spare_part_request`, renders a Request card (Requested by, Needed by, Currency,
 * Default location, Reason) and an Approval card; a sales-order inquiry renders exactly as
 * today (Order + Customer + Raise history, no Request / Approval card).
 *
 * TEST-FIRST (Phase 2). Named assumption (the brief names the SPR detail keys, not the
 * header-detail ones): the header detail carries the same spare-part keys as
 * `GET /spare-part-requests/{id}` plus the resolved names `requested_by_name` /
 * `approved_by_name` (no UUIDs in the UI). Dates read dd/mm/yyyy.
 */
import React from 'react';
import { describe, expect, it } from 'vitest';
import { render, screen, within } from '@testing-library/react';

import { OrderInquiryGeneralTab } from './OrderInquiryGeneralTab';

const REQUESTER_ID = '3f0c9a52-1111-4a2b-9c3d-000000000001';
const APPROVER_ID = '3f0c9a52-2222-4a2b-9c3d-000000000002';

const SPARE = {
  id: 'oi-1',
  inquiry_no: 'OI-2611-0007',
  inquiry_type: 'spare_part_request',
  state: 'raised',
  status: 'open',
  so_number: null,
  sales_order_id: null,
  project_sales_order_id: null,
  currency: 'MYR',
  needed_by: '2026-12-15',
  default_location: 'BRW',
  reason: 'Spare parts for the service van',
  requested_by: REQUESTER_ID,
  requested_by_name: 'Aina Requester',
  submitted_at: '2026-11-12T02:00:00',
  approved_at: '2026-11-13T03:00:00',
  approved_by: APPROVER_ID,
  approved_by_name: 'Ben Approver',
  reject_reason: null,
  raise_history: [],
} as never;

const SALES = {
  id: 'oi-2',
  inquiry_no: 'OI-2611-0001',
  inquiry_type: 'sales_order',
  so_number: 'SO000123',
  sales_order_id: 'so-1',
  so_date: '2026-11-01',
  agent_name: 'Agent A',
  customer_name: 'Example Customer',
  customer_code: 'C-001',
  raise_history: [],
} as never;

function card(title: string): HTMLElement {
  const heading = screen.getByText(title, { selector: 'h1,h2,h3,h4,div,span' });
  // The card is the nearest ancestor holding the heading and its fields.
  let node: HTMLElement | null = heading;
  while (node && !node.querySelector('dl, section, dt')) node = node.parentElement;
  return (node ?? heading) as HTMLElement;
}

describe('F2 / UAC P4: General tab of a spare part request', () => {
  it('renders a Request card with Requested by, Needed by, Currency, Default location, Reason', () => {
    render(<OrderInquiryGeneralTab header={SPARE} />);
    const request = card('Request');
    for (const label of ['Requested by', 'Needed by', 'Currency', 'Default location', 'Reason']) {
      expect(within(request).getByText(label)).toBeInTheDocument();
    }
    expect(within(request).getByText('Aina Requester')).toBeInTheDocument();
    expect(within(request).getByText('15/12/2026')).toBeInTheDocument();
    expect(within(request).getByText('MYR')).toBeInTheDocument();
    expect(within(request).getByText('BRW')).toBeInTheDocument();
    expect(within(request).getByText('Spare parts for the service van')).toBeInTheDocument();
  });

  it('renders an Approval card naming the approver', () => {
    render(<OrderInquiryGeneralTab header={SPARE} />);
    const approval = card('Approval');
    expect(within(approval).getByText('Ben Approver')).toBeInTheDocument();
  });

  it('never shows a user id', () => {
    const { container } = render(<OrderInquiryGeneralTab header={SPARE} />);
    expect(container.textContent).not.toContain(REQUESTER_ID);
    expect(container.textContent).not.toContain(APPROVER_ID);
  });

  it('a rejected request shows the reject reason in the Approval card', () => {
    const rejected = {
      ...(SPARE as object),
      state: 'rejected',
      approved_at: null,
      approved_by: null,
      approved_by_name: null,
      reject_reason: 'Use the cheaper seal',
    } as never;
    render(<OrderInquiryGeneralTab header={rejected} />);
    expect(within(card('Approval')).getByText('Use the cheaper seal')).toBeInTheDocument();
  });
});

describe('F2 / UAC P6: General tab of a sales-order inquiry is unchanged', () => {
  it('keeps Order, Customer and Raise history, and adds no Request or Approval card', () => {
    render(<OrderInquiryGeneralTab header={SALES} />);
    expect(screen.getByText('Order')).toBeInTheDocument();
    expect(screen.getByText('Customer', { selector: 'h1,h2,h3,h4,div,span' })).toBeInTheDocument();
    expect(screen.getByText('Raise history')).toBeInTheDocument();
    expect(screen.getByText('SO000123')).toBeInTheDocument();
    expect(screen.queryByText('Request')).toBeNull();
    expect(screen.queryByText('Approval')).toBeNull();
  });
});
