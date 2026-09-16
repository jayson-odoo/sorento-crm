/**
 * The three stage cards above both views (S5, R-F, AC-D5/AC-D8): Buy, Purchased,
 * Incoming, in THAT order - the furthest a unit has reached, left to right - totals off
 * the worklist summary's `kinds` facet, a click narrows, a second click clears, no
 * caption under any of them.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { OrderInquiryStrip } from './OrderInquiryStrip';
import { facetSegments } from '../../_shared/lib/orderInquiryKinds';

describe('OrderInquiryStrip (AC-D5: order and labels)', () => {
  it('renders exactly three cards, Buy, Purchased, Incoming, in that order', () => {
    render(
      <OrderInquiryStrip totals={facetSegments({ spo: '10', po: '95', buy: '116' })} active={null} onToggle={vi.fn()} />,
    );

    const cards = screen.getAllByRole('button');
    expect(cards).toHaveLength(3);
    expect(cards.map((card) => card.textContent)).toEqual([
      expect.stringContaining('Buy'),
      expect.stringContaining('Purchased'),
      expect.stringContaining('Incoming'),
    ]);
  });

  it('shows the totals off the summary facet, not a client-side count', () => {
    render(
      <OrderInquiryStrip totals={facetSegments({ spo: '10', po: '95', buy: '116' })} active={null} onToggle={vi.fn()} />,
    );

    expect(screen.getByTestId('order-inquiry-strip-qty-buy')).toHaveTextContent('116');
    expect(screen.getByTestId('order-inquiry-strip-qty-po')).toHaveTextContent('95');
    expect(screen.getByTestId('order-inquiry-strip-qty-spo')).toHaveTextContent('10');
  });

  it('reads three zero cards while the summary has not answered yet', () => {
    render(<OrderInquiryStrip totals={facetSegments(undefined)} active={null} onToggle={vi.fn()} />);

    expect(screen.getByTestId('order-inquiry-strip-qty-buy')).toHaveTextContent('0');
    expect(screen.getByTestId('order-inquiry-strip-qty-po')).toHaveTextContent('0');
    expect(screen.getByTestId('order-inquiry-strip-qty-spo')).toHaveTextContent('0');
  });

  it('clicking a card calls onToggle with that kind, and a second click clears it', () => {
    const onToggle = vi.fn();
    const { rerender } = render(
      <OrderInquiryStrip
        totals={facetSegments({ spo: '10', po: '95', buy: '116' })}
        active={null}
        onToggle={onToggle}
      />,
    );

    screen.getByTestId('order-inquiry-strip-po').click();
    expect(onToggle).toHaveBeenCalledWith('po');

    // The parent owns the toggle-off logic (OrderInquiriesClient); here we assert the
    // pressed card's own aria-pressed state, which is what the parent's toggle drives.
    rerender(
      <OrderInquiryStrip
        totals={facetSegments({ spo: '10', po: '95', buy: '116' })}
        active="po"
        onToggle={onToggle}
      />,
    );
    expect(screen.getByTestId('order-inquiry-strip-po')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('order-inquiry-strip-buy')).toHaveAttribute('aria-pressed', 'false');

    screen.getByTestId('order-inquiry-strip-po').click();
    expect(onToggle).toHaveBeenLastCalledWith('po');

    rerender(
      <OrderInquiryStrip
        totals={facetSegments({ spo: '10', po: '95', buy: '116' })}
        active={null}
        onToggle={onToggle}
      />,
    );
    expect(screen.getByTestId('order-inquiry-strip-po')).toHaveAttribute('aria-pressed', 'false');
  });

  it('disables a card reading zero - nothing in view is that kind, so there is nothing to filter to', () => {
    render(
      <OrderInquiryStrip totals={facetSegments({ spo: '0', po: '95', buy: '116' })} active={null} onToggle={vi.fn()} />,
    );

    expect(screen.getByTestId('order-inquiry-strip-spo')).toBeDisabled();
    expect(screen.getByTestId('order-inquiry-strip-po')).not.toBeDisabled();
    expect(screen.getByTestId('order-inquiry-strip-buy')).not.toBeDisabled();
  });

  it('keeps every card in its place whether it reads a quantity or zero', () => {
    render(
      <OrderInquiryStrip totals={facetSegments({ spo: '0', po: '0', buy: '0' })} active={null} onToggle={vi.fn()} />,
    );

    expect(screen.getAllByRole('button')).toHaveLength(3);
    expect(screen.getByTestId('order-inquiry-strip-spo')).toBeDisabled();
    expect(screen.getByTestId('order-inquiry-strip-po')).toBeDisabled();
    expect(screen.getByTestId('order-inquiry-strip-buy')).toBeDisabled();
  });
});

describe('OrderInquiryStrip (AC-D8: no on-screen explanation)', () => {
  it('carries no caption text under any card - the number and the label are the whole card', () => {
    render(
      <OrderInquiryStrip totals={facetSegments({ spo: '10', po: '95', buy: '116' })} active={null} onToggle={vi.fn()} />,
    );

    // No legend, no sentence, no sub-line: each card's own text is exactly its label
    // followed by its quantity (`SupplyKindCard`'s own layout puts the qty in a child
    // span the strip owns, `order-inquiry-strip-qty-<kind>`; nothing else renders).
    expect(screen.getByTestId('order-inquiry-strip-buy').textContent).toBe('Buy116');
    expect(screen.getByTestId('order-inquiry-strip-po').textContent).toBe('Purchased95');
    expect(screen.getByTestId('order-inquiry-strip-spo').textContent).toBe('Incoming10');
  });
});
