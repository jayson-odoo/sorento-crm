/**
 * OI-WHOLE-SO-CANCEL v2 (F1 leftover), red: the Lines tab State column must print each filter
 * word exactly as the filter spells it ("Waiting for CS", not "Waiting For CS"). The shared
 * pill base carries `capitalize`, so a pill that keeps it prints every word title-cased; jsdom
 * cannot compute text-transform, so the class is asserted: any pill carrying `capitalize` must
 * also carry `normal-case` (as `ReservePill` does).
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { OrderInquiryLineStatePill } from './OrderInquiryVerbPill';
import { LINE_STATUS_OPTIONS, OrderInquiryLineStatusPill } from './OrderInquiryLineStatusPill';
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

/** Each filter word with a line the State column renders it for. */
const CASES: [string, OrderInquiryLine][] = [
  ['To order', line('raised')],
  ['Waiting for CS', line('raised', { waiting_for_cs: true })],
  ['Done', line('raised', { ack_state: 'acknowledged' })],
  ['SO cancelled', line('line_cancelled', { so_cancelled: true, line_cancelled: true })],
  ['Line cancelled', line('line_cancelled', { line_cancelled: true })],
  ['Nothing to buy', line('nothing_to_buy')],
  ['Request to reserve', line('raised', { reserve_state: 'requested', requested_qty: '' })],
  ['Reserved', line('raised', { reserve_state: 'reserved' })],
  ['Not reserved', line('raised', { reserve_state: 'declined' })],
];

function readsAsTyped(el: HTMLElement) {
  const cls = el.className;
  return !cls.includes('capitalize') || cls.includes('normal-case');
}

describe('F1: the State column pills do not re-case the filter words', () => {
  it('covers every LINE_STATUS_OPTIONS word except the Rejected badge', () => {
    const covered = CASES.map(([word]) => word);
    for (const option of LINE_STATUS_OPTIONS) {
      if (option.label === 'Rejected') continue;
      expect(covered, option.label).toContain(option.label);
    }
  });

  it.each(CASES)('"%s" is printed with its own case', (word, fixture) => {
    render(<OrderInquiryLineStatusPill line={fixture} />);
    const el = screen.getByText(new RegExp(`^${word}`));
    expect(readsAsTyped(el), `class "${el.className}" would title-case "${word}"`).toBe(true);
  });

  it.each(['line_cancelled', 'so_cancelled', 'waiting_for_cs', 'nothing_to_buy', 'to_confirm'])(
    'OrderInquiryLineStatePill %s keeps its label case',
    (state) => {
      const { container } = render(<OrderInquiryLineStatePill state={state} />);
      const el = container.querySelector('span') as HTMLElement;
      expect(readsAsTyped(el), `class "${el.className}"`).toBe(true);
    },
  );
});
