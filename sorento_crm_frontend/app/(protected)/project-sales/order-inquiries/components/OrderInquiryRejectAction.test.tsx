/**
 * The per-row Reject action (AC-H5), `PLAN-scm-oi-handshake.md`.
 *
 * Three facts worth pinning: it never fires on a bare click (an `AlertDialog` opens
 * first - "confirm before every destructive action", `PRINCIPLES.md`), an empty reason is
 * refused in the dialog rather than sent to the server, and a real reason is sent to the
 * mutation the hook exposes, trimmed. `useOrderInquiryHandshake` is mocked so this is a
 * unit test of the action + dialog pair, not of the mutation's own network call.
 */
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { OrderInquiryRejectAction } from './OrderInquiryRejectAction';
import type { OrderInquiryWorklistRow } from '../../_shared/types/orderInquiry.types';

const rejectMutate = vi.fn();

vi.mock('../../_shared/hooks/useOrderInquiry', () => ({
  useOrderInquiryHandshake: () => ({
    reject: { mutate: rejectMutate, isPending: false },
  }),
}));

function row(overrides: Partial<OrderInquiryWorklistRow>): OrderInquiryWorklistRow {
  return {
    id: 'row-1',
    inquiry_no: 'OI-000101',
    so_number: 'SO385126',
    item_code: 'SRTWB5400',
    product_name: 'Wall hung basin 5400',
    qty: '10',
    state: 'raised',
    verb: 'ORDER',
    ack_state: 'awaiting',
    ...overrides,
  } as OrderInquiryWorklistRow;
}

beforeEach(() => {
  rejectMutate.mockReset();
});

describe('OrderInquiryRejectAction', () => {
  it('renders nothing for a row already rejected - there is nothing left to refuse', () => {
    render(<OrderInquiryRejectAction row={row({ ack_state: 'rejected' })} />);
    expect(screen.queryByRole('button', { name: /reject/i })).toBeNull();
  });

  it('renders the button for an awaiting, acknowledged or changed row', () => {
    for (const ack_state of ['awaiting', 'acknowledged', 'changed'] as const) {
      const { unmount } = render(<OrderInquiryRejectAction row={row({ ack_state })} />);
      expect(screen.getByRole('button', { name: /reject/i })).toBeInTheDocument();
      unmount();
    }
  });

  it('does not call the mutation on the bare click - a confirm dialog opens first', () => {
    render(<OrderInquiryRejectAction row={row({})} />);
    fireEvent.click(screen.getByRole('button', { name: /reject/i }));

    expect(rejectMutate).not.toHaveBeenCalled();
    expect(
      screen.getByRole('alertdialog', { name: /reject srtwb5400\?/i }),
    ).toBeInTheDocument();
  });

  it('refuses a blank reason rather than sending it to the mutation', () => {
    render(<OrderInquiryRejectAction row={row({})} />);
    fireEvent.click(screen.getByRole('button', { name: /reject/i }));
    fireEvent.click(screen.getByRole('button', { name: /reject row/i }));

    expect(screen.getByText('A reason is required to reject.')).toBeInTheDocument();
    expect(rejectMutate).not.toHaveBeenCalled();
  });

  it('refuses a reason of only whitespace the same way', () => {
    render(<OrderInquiryRejectAction row={row({})} />);
    fireEvent.click(screen.getByRole('button', { name: /reject/i }));
    fireEvent.change(screen.getByPlaceholderText(/why can this not be bought/i), {
      target: { value: '   ' },
    });
    fireEvent.click(screen.getByRole('button', { name: /reject row/i }));

    expect(screen.getByText('A reason is required to reject.')).toBeInTheDocument();
    expect(rejectMutate).not.toHaveBeenCalled();
  });

  it('submits the trimmed reason against this row id when one is given', () => {
    render(<OrderInquiryRejectAction row={row({ id: 'row-77' })} />);
    fireEvent.click(screen.getByRole('button', { name: /reject/i }));
    fireEvent.change(screen.getByPlaceholderText(/why can this not be bought/i), {
      target: { value: '  Factory closed until November  ' },
    });
    fireEvent.click(screen.getByRole('button', { name: /reject row/i }));

    expect(rejectMutate).toHaveBeenCalledTimes(1);
    const [payload] = rejectMutate.mock.calls[0];
    expect(payload).toEqual({ rowId: 'row-77', reason: 'Factory closed until November' });
  });

  it('closes the dialog on Cancel without ever calling the mutation', () => {
    render(<OrderInquiryRejectAction row={row({})} />);
    fireEvent.click(screen.getByRole('button', { name: /reject/i }));
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }));

    expect(rejectMutate).not.toHaveBeenCalled();
    expect(screen.queryByRole('alertdialog')).toBeNull();
  });
});
