/**
 * The Acknowledged column's four readings (AC-H2/AC-H5/AC-H8), `PLAN-scm-oi-handshake.md`.
 *
 * One test per state - a buyer scanning this column needs a different fact from each of
 * them - plus the truncate + title pair the ADR mandates for any long text in a fixed-
 * width DataGrid cell (`documentation/reference/ADR-PRODUCT-STANDARDS.md`).
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { OrderInquiryAckCell } from './OrderInquiryAckCell';
import type { OrderInquiryWorklistRow } from '../../_shared/types/orderInquiry.types';

function row(overrides: Partial<OrderInquiryWorklistRow>): OrderInquiryWorklistRow {
  return {
    id: 'row-1',
    inquiry_no: 'OI-000101',
    so_date: null,
    so_number: 'SO385126',
    item_code: 'SRTWB5400',
    product_name: 'Wall hung basin 5400',
    qty: '10',
    delivery_date: null,
    project_customer: null,
    supplier: null,
    supplier_id: null,
    po_number: null,
    state: 'raised',
    raised_at: null,
    raised_by_name: null,
    verb: 'ORDER',
    note: null,
    ...overrides,
  } as OrderInquiryWorklistRow;
}

describe('OrderInquiryAckCell', () => {
  it('reads Awaiting for a row nobody has touched, no `ack_state` at all', () => {
    render(<OrderInquiryAckCell row={row({})} />);
    expect(screen.getByText('Awaiting')).toBeInTheDocument();
  });

  it('reads Acknowledged with who and when, truncated with the same text as its title', () => {
    render(
      <OrderInquiryAckCell
        row={row({
          ack_state: 'acknowledged',
          acknowledged_by_name: 'Joey Ang',
          acknowledged_at: '2026-08-27T01:56:00',
        })}
      />,
    );
    expect(screen.getByText('Acknowledged')).toBeInTheDocument();
    const detail = screen.getByText(/Joey Ang/);
    expect(detail).toHaveClass('truncate');
    expect(detail.getAttribute('title')).toBe(detail.textContent);
  });

  it('falls back to "Purchasing" when an acknowledged row carries no name', () => {
    render(
      <OrderInquiryAckCell
        row={row({ ack_state: 'acknowledged', acknowledged_by_name: null })}
      />,
    );
    expect(screen.getByText('Purchasing')).toBeInTheDocument();
  });

  it('reads Changed with the date, and draws the Was / Now table when the note parses', () => {
    render(
      <OrderInquiryAckCell
        row={row({
          ack_state: 'changed',
          changed_at: '2026-08-27',
          note: 'Was 10 on 2026-08-10',
          qty: '20',
          delivery_date: '2026-08-20',
        })}
      />,
    );
    expect(screen.getByText(/^Changed/)).toBeInTheDocument();
    expect(screen.getByTestId('board-change-row-1')).toBeInTheDocument();
    // Was on the left, Now on the right - the same table the board draws for a planning
    // change, so the two screens say a change the same way.
    expect(screen.getByText('10')).toBeInTheDocument();
    expect(screen.getByText('20')).toBeInTheDocument();
  });

  it('reads plain Changed with no table when the note carries nothing to parse', () => {
    render(
      <OrderInquiryAckCell
        row={row({ ack_state: 'changed', changed_at: null, note: 'Auto: decision_confirm' })}
      />,
    );
    expect(screen.getByText('Changed')).toBeInTheDocument();
    expect(screen.queryByTestId('board-change-row-1')).toBeNull();
  });

  it('reads Rejected with the reason and who, truncated with the same text as its title', () => {
    render(
      <OrderInquiryAckCell
        row={row({
          ack_state: 'rejected',
          rejected_by_name: 'Joey Ang',
          rejected_reason: 'Factory closed until November',
        })}
      />,
    );
    expect(screen.getByText('Rejected')).toBeInTheDocument();
    const detail = screen.getByText('Joey Ang: Factory closed until November');
    expect(detail).toHaveClass('truncate');
    expect(detail.getAttribute('title')).toBe(
      'Rejected: Factory closed until November',
    );
  });

  it('reads a rejection with no reason as just "Rejected by <name>"', () => {
    render(
      <OrderInquiryAckCell
        row={row({
          ack_state: 'rejected',
          rejected_by_name: 'Joey Ang',
          rejected_reason: '   ',
        })}
      />,
    );
    expect(screen.getByText('Rejected by Joey Ang')).toBeInTheDocument();
  });
});
