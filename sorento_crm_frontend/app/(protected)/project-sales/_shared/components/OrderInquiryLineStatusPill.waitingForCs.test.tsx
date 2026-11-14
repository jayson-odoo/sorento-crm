/**
 * OI-WHOLE-SO-CANCEL v2 (AC-V2-5), red: the shared line status pill (OI Lines tab and the
 * Sales Order line cell) prints "Waiting for CS" / "SO cancelled" ahead of "Line cancelled".
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { OrderInquiryLineStatusPill } from './OrderInquiryLineStatusPill';
import type { OrderInquiryLine } from '../lib/orderInquiryLineFold';

function line(state: string, over: Record<string, unknown> = {}): OrderInquiryLine {
  const primary = {
    id: 'row-1',
    qty: '10',
    state: 'raised',
    ack_state: 'awaiting',
    verb: 'ORDER',
    reserve_state: null,
    ...over,
  };
  return {
    key: 'row:row-1',
    lineNo: 1,
    rows: [primary],
    liveRows: [primary],
    historyRows: [],
    waitingUsedRows: [],
    primary,
    instructionRow: primary,
    state,
    lineCancelled: state === 'line_cancelled',
    muted: false,
    soQty: 10,
  } as unknown as OrderInquiryLine;
}

describe('AC-V2-5: OrderInquiryLineStatusPill', () => {
  it('reads "Waiting for CS" for a live line whose row is waiting', () => {
    render(<OrderInquiryLineStatusPill line={line('raised', { waiting_for_cs: true })} />);
    expect(screen.getByText('Waiting for CS')).toBeInTheDocument();
  });

  it('reads "Waiting for CS" for a removed (line cancelled) line until CS confirms', () => {
    render(
      <OrderInquiryLineStatusPill
        line={line('line_cancelled', { waiting_for_cs: true, line_cancelled: true })}
      />,
    );
    expect(screen.getByText('Waiting for CS')).toBeInTheDocument();
    expect(screen.queryByText('Line cancelled')).not.toBeInTheDocument();
  });

  it('reads "SO cancelled" for a cancelled SO that is not waiting', () => {
    render(
      <OrderInquiryLineStatusPill
        line={line('line_cancelled', { so_cancelled: true, waiting_for_cs: false, line_cancelled: true })}
      />,
    );
    expect(screen.getByText('SO cancelled')).toBeInTheDocument();
  });

  it('keeps "Line cancelled" for any other cancelled line', () => {
    render(
      <OrderInquiryLineStatusPill
        line={line('line_cancelled', { so_cancelled: false, waiting_for_cs: false, line_cancelled: true })}
      />,
    );
    expect(screen.getByText('Line cancelled')).toBeInTheDocument();
  });
});
