/**
 * OI-WHOLE-SO-CANCEL v2 (waiting change detail, crew decision 12 Nov), red: the shared line
 * status pill (OI Lines tab State cell, Sales Order line cell) says WHAT a waiting line waits
 * on. Date / qty: "Waiting for CS · date 18/12/2026 -> 17/01/2027" / "Waiting for CS · qty 10 -> 7".
 * Any SO-side cancel, delete or line removal: the EXISTING line-cancelled pill (same class as a
 * plain cancelled line's) plus a separate "Waiting for CS" marker, never "SO cancelled".
 * The filter word for such a line stays "Waiting for CS" (and also matches "Line cancelled").
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import {
  LINE_STATUS_OPTIONS,
  OrderInquiryLineStatusPill,
  lineStatusValue,
  lineStatusWord,
} from './OrderInquiryLineStatusPill';
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

const waitingCancelled = (kind: 'so_cancelled' | 'line_removed') =>
  line('line_cancelled', {
    line_cancelled: true,
    waiting_for_cs: true,
    waiting_change: [{ kind, was: null, now: null }],
    ...(kind === 'so_cancelled' ? { so_cancelled: true } : {}),
  });

describe('the line pill says what a waiting line waits on', () => {
  it('reads the date change', () => {
    render(
      <OrderInquiryLineStatusPill
        line={line('raised', {
          waiting_for_cs: true,
          waiting_change: [{ kind: 'date', was: '18/12/2026', now: '17/01/2027' }],
        })}
      />,
    );
    expect(screen.getByText('Waiting for CS · date 18/12/2026 -> 17/01/2027')).toBeInTheDocument();
  });

  it('joins a combined date and qty change, truncated with the full text in the title', () => {
    render(
      <OrderInquiryLineStatusPill
        line={line('raised', {
          waiting_for_cs: true,
          waiting_change: [
            { kind: 'date', was: '18/12/2026', now: '17/01/2027' },
            { kind: 'qty', was: '10', now: '7' },
          ],
        })}
      />,
    );
    const full = 'Waiting for CS · date 18/12/2026 -> 17/01/2027 · qty 10 -> 7';
    const pill = screen.getByText(full);
    expect(pill.className).toContain('truncate');
    expect(pill).toHaveAttribute('title', expect.stringContaining(full));
  });

  it('reads the qty change', () => {
    render(
      <OrderInquiryLineStatusPill
        line={line('raised', {
          waiting_for_cs: true,
          waiting_change: [{ kind: 'qty', was: '10', now: '7' }],
        })}
      />,
    );
    expect(screen.getByText('Waiting for CS · qty 10 -> 7')).toBeInTheDocument();
  });

  it.each(['so_cancelled', 'line_removed'] as const)(
    'a waiting %s change renders the existing line-cancelled pill beside a Waiting for CS marker',
    (kind) => {
      const plain = render(<OrderInquiryLineStatusPill line={line('line_cancelled', { line_cancelled: true })} />);
      const plainClass = screen.getByText('Line cancelled').className;
      plain.unmount();

      render(<OrderInquiryLineStatusPill line={waitingCancelled(kind)} />);
      expect(screen.getByText('Line cancelled').className).toBe(plainClass);
      expect(screen.getByText('Waiting for CS')).toBeInTheDocument();
      expect(screen.queryByText('SO cancelled')).not.toBeInTheDocument();
    },
  );

  it('after CS confirms, only the plain line-cancelled pill remains', () => {
    render(
      <OrderInquiryLineStatusPill
        line={line('line_cancelled', { line_cancelled: true, waiting_for_cs: false, waiting_change: null })}
      />,
    );
    expect(screen.getByText('Line cancelled')).toBeInTheDocument();
    expect(screen.queryByText('Waiting for CS')).not.toBeInTheDocument();
  });

  it('the filter keeps its words: a waiting date line is "Waiting for CS"; both options exist', () => {
    const labels = LINE_STATUS_OPTIONS.map((o) => o.label);
    expect(labels).toContain('Waiting for CS');
    expect(labels).toContain('Line cancelled');
    const dateLine = line('raised', {
      waiting_for_cs: true,
      waiting_change: [{ kind: 'date', was: '18/12/2026', now: '17/01/2027' }],
    });
    expect(lineStatusWord(dateLine)).toBe('Waiting for CS');
    expect(lineStatusValue(dateLine)).toBe('Waiting for CS');
  });
});
