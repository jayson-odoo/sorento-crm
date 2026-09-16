/**
 * The delivery-month tab strip (S2, AC-M1/AC-M2 - PLAN-scm-oi-worklist-excel-parity.md
 * R-G): "All" first, one tab per month with rows, each carrying its own count; clicking
 * a tab sets `delivery_month`, "All" clears it.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { OrderInquiryMonthStrip } from './OrderInquiryMonthStrip';
import type { OrderInquiryMonthTotal } from '../../_shared/types/orderInquiry.types';

function month(over: Partial<OrderInquiryMonthTotal> = {}): OrderInquiryMonthTotal {
  return { month: '2026-01', label: 'JAN 26', rows: 0, qty: '0', ...over };
}

describe('OrderInquiryMonthStrip (AC-M1)', () => {
  it('renders "All" first, then one tab per month that has rows, each with its count', () => {
    render(
      <OrderInquiryMonthStrip
        months={[
          month({ month: '2026-01', label: 'JAN 26', rows: 5 }),
          month({ month: '2026-02', label: 'FEB 26', rows: 0 }),
          month({ month: '2026-03', label: 'MAR 26', rows: 3 }),
        ]}
        active=""
        onSelect={vi.fn()}
      />,
    );

    const strip = screen.getByTestId('order-inquiry-month-strip');
    const buttons = strip.querySelectorAll('button');
    expect(buttons).toHaveLength(3); // All, JAN 26, MAR 26 - FEB 26 has no rows
    expect(buttons[0].textContent).toBe('All');
    expect(buttons[1].textContent).toBe('JAN 26 (5)');
    expect(buttons[2].textContent).toBe('MAR 26 (3)');
  });

  it('renders nothing at all when no month has any rows', () => {
    render(
      <OrderInquiryMonthStrip
        months={[month({ rows: 0 })]}
        active=""
        onSelect={vi.fn()}
      />,
    );

    expect(screen.queryByTestId('order-inquiry-month-strip')).not.toBeInTheDocument();
  });

  it('marks the active month selected via aria-pressed, and "All" when nothing is chosen', () => {
    render(
      <OrderInquiryMonthStrip
        months={[month({ month: '2026-01', label: 'JAN 26', rows: 5 })]}
        active="2026-01"
        onSelect={vi.fn()}
      />,
    );

    expect(screen.getByTestId('order-inquiry-month-tab-JAN 26')).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(screen.getByTestId('order-inquiry-month-tab-All')).toHaveAttribute(
      'aria-pressed',
      'false',
    );
  });
});

describe('OrderInquiryMonthStrip (AC-M2)', () => {
  it('clicking a month tab calls onSelect with that YYYY-MM value', () => {
    const onSelect = vi.fn();
    render(
      <OrderInquiryMonthStrip
        months={[month({ month: '2026-03', label: 'MAR 26', rows: 3 })]}
        active=""
        onSelect={onSelect}
      />,
    );

    screen.getByTestId('order-inquiry-month-tab-MAR 26').click();

    expect(onSelect).toHaveBeenCalledWith('2026-03');
  });

  it('clicking "All" calls onSelect with an empty string, clearing the month', () => {
    const onSelect = vi.fn();
    render(
      <OrderInquiryMonthStrip
        months={[month({ month: '2026-03', label: 'MAR 26', rows: 3 })]}
        active="2026-03"
        onSelect={onSelect}
      />,
    );

    screen.getByTestId('order-inquiry-month-tab-All').click();

    expect(onSelect).toHaveBeenCalledWith('');
  });
});
