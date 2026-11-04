/**
 * OI-ONE-DELIVERY-DATE, AC-E1..E3: a Delivery date cell whose row has a Was shows the same
 * amber "What changed" icon the SO line uses (`BoardChangeTable`); the lightbox is titled
 * "What changed, <SO> (Line <n>)" and its Date row reads Was = `previous_delivery_date`,
 * Now = `delivery_date`. No Was, no icon; the "Changed" pill on `ack_state = changed` stays.
 *
 * TEST-FIRST: today the cell prints the date and the pill only, so the icon queries are the
 * red.
 */
import React from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { formatDateInMalaysia } from '@/lib/helpers';
import type { OrderInquiryWorklistRow } from '../../_shared/types/orderInquiry.types';
import { DeliveryDateCell } from './orderInquiryWorklistColumns';

function worklistRow(over: Partial<OrderInquiryWorklistRow> = {}): OrderInquiryWorklistRow {
  return {
    id: 'row-1',
    qty: '10',
    state: 'raised',
    verb: 'ORDER',
    links: [],
    linked_qty: '0',
    so_number: 'SO397450',
    line_no: 312,
    item_code: 'B2155-NL-BLUE',
    ...over,
  } as OrderInquiryWorklistRow;
}

describe('DeliveryDateCell: the Was icon (OI-ONE-DELIVERY-DATE)', () => {
  it('AC-E1: a row with a Was shows the BoardChangeTable icon beside the Now date', () => {
    render(
      <DeliveryDateCell
        row={worklistRow({ delivery_date: '2027-01-07', previous_delivery_date: '2026-07-01' })}
      />,
    );

    expect(screen.getByText(formatDateInMalaysia('2027-01-07'))).toBeTruthy();
    expect(screen.getByTestId('board-change-icon-row-1')).toBeTruthy();
  });

  it('AC-E2: the icon opens the lightbox with Was and Now on the Date row', () => {
    render(
      <DeliveryDateCell
        row={worklistRow({ delivery_date: '2027-01-07', previous_delivery_date: '2026-07-01' })}
      />,
    );

    fireEvent.click(screen.getByTestId('board-change-icon-row-1'));

    const dialog = screen.getByTestId('board-change-dialog');
    expect(within(dialog).getByText(/What changed, SO397450 \(Line 312\)/)).toBeTruthy();
    expect(within(dialog).getByText(formatDateInMalaysia('2026-07-01'))).toBeTruthy();
    expect(within(dialog).getByText(formatDateInMalaysia('2027-01-07'))).toBeTruthy();
  });

  it('AC-E3: no previous_delivery_date, no icon', () => {
    render(<DeliveryDateCell row={worklistRow({ delivery_date: '2027-01-07' })} />);

    expect(screen.getByText(formatDateInMalaysia('2027-01-07'))).toBeTruthy();
    expect(screen.queryByTestId('board-change-icon-row-1')).toBeNull();
  });

  it('AC-E3: a previous date equal to the shown date is no Was, so no icon', () => {
    render(
      <DeliveryDateCell
        row={worklistRow({ delivery_date: '2027-01-07', previous_delivery_date: '2027-01-07' })}
      />,
    );

    expect(screen.queryByTestId('board-change-icon-row-1')).toBeNull();
  });

  it('AC-E3: the Changed pill stays on ack_state = changed, beside the icon', () => {
    render(
      <DeliveryDateCell
        row={worklistRow({
          delivery_date: '2027-01-07',
          previous_delivery_date: '2026-07-01',
          ack_state: 'changed',
        })}
      />,
    );

    expect(screen.getByTestId('delivery-date-changed-row-1')).toBeTruthy();
    expect(screen.getByTestId('board-change-icon-row-1')).toBeTruthy();
  });
});
