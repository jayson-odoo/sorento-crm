/**
 * The product page has to answer "what does this cost, and how do you know".
 *
 * > "I want to know where it derives from, like is it last purchase price, if yes, what's
 * >  the PO and who is the supplier"
 *
 * A product with no orders is the case that sent the user looking in the first place, so
 * the empty state says what is true rather than leaving a blank table.
 */
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { ProductPurchaseHistory } from '../../services/productService';

const useProductPurchaseHistory = vi.fn();
vi.mock('../../hooks/useProducts', () => ({
  useProductPurchaseHistory: (...args: unknown[]) => useProductPurchaseHistory(...args),
}));
const push = vi.fn();
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }));

import ProductPurchaseHistoryTab from './ProductPurchaseHistoryTab';

const history = (over: Partial<ProductPurchaseHistory> = {}): ProductPurchaseHistory => ({
  product_id: 'p1',
  lines: [
    {
      purchase_order_id: 'po-1',
      po_number: 'PO26-0044',
      issue_date: '2026-01-09',
      status: 'active',
      supplier_code: 'SJ',
      supplier_name: 'Sanjiang',
      qty_ordered: 120,
      qty_received: 0,
      unit_cost: 88,
      currency: 'MYR',
    },
  ],
  total: 1,
  shown: 1,
  cost: {
    status: 'ok',
    unit_cost: 88,
    currency: 'MYR',
    po_number: 'PO26-0044',
    purchase_order_id: 'po-1',
    supplier_code: 'SJ',
    supplier_name: 'Sanjiang',
    issue_date: '2026-01-09',
  },
  ...over,
});

function stub(data: ProductPurchaseHistory | undefined, extra: Record<string, unknown> = {}) {
  useProductPurchaseHistory.mockReturnValue({
    data,
    isLoading: false,
    isError: false,
    error: null,
    ...extra,
  });
}

beforeEach(() => {
  useProductPurchaseHistory.mockReset();
  push.mockReset();
});

describe('ProductPurchaseHistoryTab', () => {
  it('shows the order, the supplier, the quantity and the price paid', () => {
    stub(history());
    render(<ProductPurchaseHistoryTab productId="p1" />);

    expect(screen.getByText('PO26-0044')).toBeInTheDocument();
    expect(screen.getByText('Sanjiang')).toBeInTheDocument();
    expect(screen.getByText('120')).toBeInTheDocument();
    expect(screen.getByText('RM 88.00')).toBeInTheDocument();
    expect(screen.getByText('09/01/2026')).toBeInTheDocument();
  });

  it('states that a never-purchased product has no cost from history', () => {
    stub(
      history({
        lines: [],
        total: 0,
        shown: 0,
        cost: {
          status: 'never_purchased',
          unit_cost: null,
          currency: null,
          po_number: null,
          purchase_order_id: null,
          supplier_code: null,
          supplier_name: null,
          issue_date: null,
        },
      }),
    );
    render(<ProductPurchaseHistoryTab productId="p1" />);

    expect(screen.getByText(/never been purchased/i)).toBeInTheDocument();
    expect(screen.getByText(/no cost from history/i)).toBeInTheDocument();
  });

  it('says how many lines it did not show, so the cap is never silent', () => {
    stub(history({ total: 214, shown: 1 }));
    render(<ProductPurchaseHistoryTab productId="p1" />);

    expect(screen.getByText(/most recent of 214 purchase lines/i)).toBeInTheDocument();
  });

  it('keeps a foreign-currency order in its own currency rather than implying ringgit', () => {
    stub(
      history({
        lines: [{ ...history().lines[0], unit_cost: 143.5, currency: 'CNY' }],
      }),
    );
    render(<ProductPurchaseHistoryTab productId="p1" />);

    expect(screen.getByText('143.50 CNY')).toBeInTheDocument();
  });

  it('names an order that has no supplier instead of leaving the cell blank', () => {
    stub(
      history({ lines: [{ ...history().lines[0], supplier_name: null, supplier_code: null }] }),
    );
    render(<ProductPurchaseHistoryTab productId="p1" />);

    expect(screen.getByText(/no supplier on the order/i)).toBeInTheDocument();
  });

  it('surfaces a load failure rather than looking like an empty history', () => {
    stub(undefined, { isError: true, error: new Error('Failed to load purchase history') });
    render(<ProductPurchaseHistoryTab productId="p1" />);

    expect(screen.getByText(/Failed to load purchase history/i)).toBeInTheDocument();
    expect(screen.queryByText(/never been purchased/i)).not.toBeInTheDocument();
  });
});

describe('a figure with no currency behind it', () => {
  // Every other price on the page is ringgit, so a bare number reads as ringgit. It may
  // not be, and a wrong currency is a wrong price.
  it('marks a cost whose order recorded no currency', () => {
    stub(history({ lines: [{ ...history().lines[0], currency: null }] }));
    render(<ProductPurchaseHistoryTab productId="p1" />);

    const cell = screen.getByText('88.00');
    expect(cell).toHaveAttribute('title', expect.stringMatching(/currency not recorded/i));
  });
});
