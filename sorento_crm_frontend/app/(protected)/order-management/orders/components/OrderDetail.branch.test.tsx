/**
 * DO-BRANCH-NAME (owner, 13 Oct 2026): the synced AutoCount branch name is visible on the
 * delivery order detail so the owner can cross-check what the chatbot says.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import OrderDetail from './OrderDetail';

const useOrder = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(''),
  usePathname: () => '/order-management/orders/o-1',
}));
vi.mock('../hooks/useOrders', () => ({
  useOrder: (...a: unknown[]) => useOrder(...a),
  ordersPagerQuery: vi.fn(),
}));
vi.mock('../actions', () => ({
  useOrderActions: () => ({ actions: [], dialogs: null, pending: false }),
}));
vi.mock('@/hooks/useDeletedRecordGuard', () => ({ useDeletedRecordGuard: () => false }));
vi.mock('@/components/common/DetailActions', () => ({ default: () => null }));
const linesCardProps = vi.fn();
vi.mock('./OrderLinesCard', () => ({
  default: (props: Record<string, unknown>) => {
    linesCardProps(props);
    return null;
  },
}));
let granted = new Set<string>();
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => granted.has(slug),
}));
vi.mock('./OrderFulfilledComplaintsCard', () => ({ default: () => null }));
vi.mock('@/app/(protected)/finance/billing-documents/components/OrderInvoices', () => ({
  OrderInvoices: (props: { deliveryOrderId?: string }) => (
    <div data-testid="order-invoices" data-delivery-order={props.deliveryOrderId} />
  ),
}));
vi.mock('../../shared/related/RelatedDocumentsPanel', () => ({
  RelatedDocumentsPanel: (props: { kind: string; id: string }) => (
    <div data-testid="related-panel" data-kind={props.kind} data-id={props.id} />
  ),
}));

function mockOrder(overrides: Record<string, unknown>) {
  useOrder.mockReturnValue({
    data: {
      id: 'o-1',
      order_number: 'DO-AC-0001',
      debtor_code: '300-AC',
      debtor_name: 'HANLIM TRADING SDN BHD',
      subtotal_amount: 0,
      discount_amount: 0,
      tax_amount: 0,
      total_amount: 0,
      ...overrides,
    },
    isLoading: false,
  });
}

function branchValue(): string | null {
  const label = screen.getByText('Branch');
  const cell = label.parentElement as HTMLElement;
  return within(cell).getAllByText(/.+/)[1]?.textContent ?? null;
}

beforeEach(() => {
  useOrder.mockReset();
  linesCardProps.mockReset();
  granted = new Set();
});

describe('Delivery order detail: Branch', () => {
  it('shows the branch name', () => {
    mockOrder({ branch_name: 'KLCC SITE OFFICE' });
    render(<OrderDetail orderId="o-1" listSearch="" />);
    expect(branchValue()).toBe('KLCC SITE OFFICE');
  });

  it('shows the branch name on the Delivery tab too', async () => {
    mockOrder({ branch_name: 'KLCC SITE OFFICE' });
    render(<OrderDetail orderId="o-1" listSearch="" />);
    await userEvent.click(screen.getByRole('tab', { name: 'Delivery' }));
    expect(screen.getByRole('tab', { name: 'Delivery' })).toHaveAttribute('aria-selected', 'true');
    expect(branchValue()).toBe('KLCC SITE OFFICE');
  });

  it('shows a dash when the DO has no branch name', () => {
    mockOrder({ branch_name: null });
    render(<OrderDetail orderId="o-1" listSearch="" />);
    expect(branchValue()).toBe('-');
  });
});

// DO-SO-LINK-SURFACE: the SO column links only for a user who can open sales orders.
describe('Delivery order detail: SO column permission', () => {
  it('lets the SO column link when the user can open sales orders', async () => {
    granted = new Set(['scm.dashboard.view']);
    mockOrder({ lines: [] });
    render(<OrderDetail orderId="o-1" listSearch="" />);
    await userEvent.click(screen.getByRole('tab', { name: 'Lines' }));
    expect(linesCardProps).toHaveBeenLastCalledWith(expect.objectContaining({ canOpenSo: true }));
  });

  it('keeps the SO column as text when the user cannot', async () => {
    mockOrder({ lines: [] });
    render(<OrderDetail orderId="o-1" listSearch="" />);
    await userEvent.click(screen.getByRole('tab', { name: 'Lines' }));
    expect(linesCardProps).toHaveBeenLastCalledWith(expect.objectContaining({ canOpenSo: false }));
  });
});

// DOC-RELATIONS (owner 27 Oct): the DO detail takes the SO detail's tab shape and shares its
// Invoices grid and Related table.
describe('Delivery order detail: tabs like the sales order', () => {
  it('carries General, Lines, Delivery, Invoices, Related in that order', () => {
    granted = new Set(['finance.billing_documents.view']);
    mockOrder({ lines: [] });
    render(<OrderDetail orderId="o-1" listSearch="" />);
    expect(screen.getAllByRole('tab').map((t) => t.textContent)).toEqual([
      'General',
      'Lines',
      'Delivery',
      'Invoices',
      'Related',
    ]);
    expect(screen.getByRole('tab', { name: 'General' })).toHaveAttribute('aria-selected', 'true');
  });

  it('hides Invoices without the billing view slug', () => {
    mockOrder({ lines: [] });
    render(<OrderDetail orderId="o-1" listSearch="" />);
    expect(screen.queryByRole('tab', { name: 'Invoices' })).toBeNull();
  });

  it('shows the shared Invoices grid for this delivery order', async () => {
    granted = new Set(['finance.billing_documents.view']);
    mockOrder({ lines: [] });
    render(<OrderDetail orderId="o-1" listSearch="" />);
    await userEvent.click(screen.getByRole('tab', { name: 'Invoices' }));
    expect(screen.getByTestId('order-invoices')).toHaveAttribute('data-delivery-order', 'o-1');
  });

  it('shows the shared Related table for this delivery order', async () => {
    mockOrder({ lines: [] });
    render(<OrderDetail orderId="o-1" listSearch="" />);
    await userEvent.click(screen.getByRole('tab', { name: 'Related' }));
    const panel = screen.getByTestId('related-panel');
    expect(panel).toHaveAttribute('data-kind', 'delivery_order');
    expect(panel).toHaveAttribute('data-id', 'o-1');
  });

  it('keeps the financial summary on General', () => {
    mockOrder({ lines: [] });
    render(<OrderDetail orderId="o-1" listSearch="" />);
    expect(screen.getByText('Financial summary')).toBeInTheDocument();
    expect(screen.getByText('Delivery order information')).toBeInTheDocument();
  });
});
