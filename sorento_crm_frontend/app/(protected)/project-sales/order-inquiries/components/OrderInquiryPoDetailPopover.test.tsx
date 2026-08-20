/**
 * The "PO no" cell's popup (the captain, 20 Aug): a placed worklist row's purchase order
 * number opens that PO's own header and every line, not only the one the row happened to
 * be tagged to.
 */
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { OrderInquiryPoDetail } from '../../_shared/types/orderInquiry.types';

// jsdom polyfills for Radix Popover (mirrors DemandDrillPopover.test.tsx).
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

const hooks = vi.hoisted(() => ({ useOrderInquiryPoDetail: vi.fn() }));
vi.mock('../../_shared/hooks/useOrderInquiry', () => hooks);

import { OrderInquiryPoDetailPopover } from './OrderInquiryPoDetailPopover';

const DETAIL: OrderInquiryPoDetail = {
  id: 'po-1',
  po_number: '202601-S0015',
  supplier_code: 'SUP-01',
  supplier_name: 'Dafuyuan',
  expected_date: '2026-09-01',
  status: 'active',
  lines: [
    {
      sku: 'SRTWC8605',
      product_name: 'Close coupled WC 8605',
      qty_ordered: '40',
      qty_received: '15',
      remaining: '25',
      location: 'BRW-BB',
    },
    {
      sku: 'SRTWB5400',
      product_name: 'Wall hung basin 5400',
      qty_ordered: '10',
      qty_received: '0',
      remaining: '10',
      location: null,
    },
  ],
};

function state(over: Record<string, unknown> = {}) {
  return { data: undefined, isLoading: false, isError: false, ...over };
}

function renderPopover(hookState: ReturnType<typeof state>) {
  hooks.useOrderInquiryPoDetail.mockReturnValue(hookState);
  render(<OrderInquiryPoDetailPopover poId="po-1" poNumber="202601-S0015" />);
}

function openPopover() {
  fireEvent.click(screen.getByRole('button', { name: '202601-S0015' }));
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('OrderInquiryPoDetailPopover - the trigger', () => {
  it('renders the PO number as the trigger and nothing else until it is opened', () => {
    renderPopover(state());
    expect(screen.getByRole('button', { name: '202601-S0015' })).toBeInTheDocument();
    expect(screen.queryByText('Dafuyuan')).not.toBeInTheDocument();
  });

  it('does not fetch the detail until the popover is opened', () => {
    renderPopover(state());
    expect(hooks.useOrderInquiryPoDetail).toHaveBeenLastCalledWith('po-1', { enabled: false });
    openPopover();
    expect(hooks.useOrderInquiryPoDetail).toHaveBeenLastCalledWith('po-1', { enabled: true });
  });
});

describe('OrderInquiryPoDetailPopover - states', () => {
  it('shows a skeleton while the detail is loading', () => {
    renderPopover(state({ isLoading: true }));
    openPopover();
    expect(screen.getByTestId('po-detail-po-1').querySelector('.animate-pulse')).toBeTruthy();
  });

  it('says the load failed rather than showing a blank popup', () => {
    renderPopover(state({ isError: true }));
    openPopover();
    expect(screen.getByText('Could not load this purchase order.')).toBeInTheDocument();
  });
});

describe('OrderInquiryPoDetailPopover - the header and lines', () => {
  it('names the supplier, the expected date and the status', () => {
    renderPopover(state({ data: DETAIL }));
    openPopover();
    expect(screen.getByText('SUP-01 - Dafuyuan')).toBeInTheDocument();
    expect(screen.getByText('active')).toBeInTheDocument();
  });

  it('lists every line - sku, product name, ordered, received, remaining, location', () => {
    renderPopover(state({ data: DETAIL }));
    openPopover();
    expect(screen.getByText('SRTWC8605')).toBeInTheDocument();
    expect(screen.getByText('Close coupled WC 8605')).toBeInTheDocument();
    expect(screen.getByText('40')).toBeInTheDocument();
    expect(screen.getByText('15')).toBeInTheDocument();
    expect(screen.getByText('25')).toBeInTheDocument();
    expect(screen.getByText('BRW-BB')).toBeInTheDocument();
    // The second line's product name equals nothing shared with its sku, and it carries
    // no location - rendered as a dash, not left silently blank.
    expect(screen.getByText('SRTWB5400')).toBeInTheDocument();
    expect(screen.getByText('Wall hung basin 5400')).toBeInTheDocument();
  });

  it('never renders an internal id, only the human identifiers', () => {
    renderPopover(state({ data: DETAIL }));
    openPopover();
    const content = screen.getByTestId('po-detail-po-1');
    expect(content.textContent ?? '').not.toMatch(/[0-9a-f]{8}-[0-9a-f]{4}-/i);
  });
});
