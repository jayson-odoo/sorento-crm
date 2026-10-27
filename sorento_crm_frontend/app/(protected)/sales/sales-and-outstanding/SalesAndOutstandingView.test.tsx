/**
 * REPORT-UNIFY slice 4: the "Sales & outstanding" screen is the kernel ReportPage with one line tab per basis. The tab
 * is held in the URL (`?tab=`), picks the report key, and a tab the user lacks the permission for is not shown.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

const state = vi.hoisted(() => ({
  tab: null as string | null,
  perms: new Set<string>(),
  replace: vi.fn(),
}));

vi.mock('next/navigation', () => ({
  usePathname: () => '/sales/sales-and-outstanding',
  useRouter: () => ({ push: vi.fn(), replace: state.replace }),
  useSearchParams: () => ({
    get: (key: string) => (key === 'tab' ? state.tab : null),
    toString: () => (state.tab ? `tab=${state.tab}` : ''),
  }),
}));

vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => state.perms.has(slug),
}));

// The page body is the kernel's; here only the report it was given and the strip under its header matter.
vi.mock('@/components/reports/ReportPage', () => ({
  ReportPage: ({
    reportKey,
    title,
    belowHeader,
  }: {
    reportKey: string;
    title?: string;
    belowHeader?: React.ReactNode;
  }) => (
    <div>
      <h1>{title}</h1>
      <div data-testid="report-key">{reportKey}</div>
      {belowHeader}
    </div>
  ),
}));

import { SalesAndOutstandingView } from './SalesAndOutstandingView';

const ALL = ['sales.reports.view', 'order_management.orders.view', 'finance.billing_documents.view'];
const LABELS = ['Invoiced', 'Delivered', 'Ordered', 'Undelivered orders', 'Pending delivery', 'Unpaid invoices'];

beforeEach(() => {
  state.tab = null;
  state.perms = new Set(ALL);
  state.replace.mockClear();
});

describe('SalesAndOutstandingView', () => {
  it('renders one tab per basis under the page title and opens on Invoiced', () => {
    render(<SalesAndOutstandingView />);
    expect(screen.getByRole('heading', { name: 'Sales & outstanding' })).toBeTruthy();
    expect(screen.getAllByRole('tab').map((t) => t.textContent)).toEqual(LABELS);
    expect(screen.getByTestId('report-key').textContent).toBe('sales_invoiced_ask');
  });

  it.each([
    ['delivered', 'sales_order_lines_ask_delivered'],
    ['ordered', 'sales_order_lines_ask_ordered'],
    ['undelivered', 'sales_order_lines_ask_outstanding'],
    ['pending-delivery', 'delivery_order_lines_pending'],
    ['unpaid', 'unpaid_documents'],
  ])('the ?tab=%s URL shows the %s report', (tab, reportKey) => {
    state.tab = tab;
    render(<SalesAndOutstandingView />);
    expect(screen.getByTestId('report-key').textContent).toBe(reportKey);
  });

  it('a tab click writes the tab to the URL, and Invoiced (the landing tab) writes none', () => {
    state.tab = 'delivered';
    render(<SalesAndOutstandingView />);
    fireEvent.mouseDown(screen.getByRole('tab', { name: 'Unpaid invoices' }));
    fireEvent.click(screen.getByRole('tab', { name: 'Unpaid invoices' }));
    expect(state.replace).toHaveBeenCalledWith('/sales/sales-and-outstanding?tab=unpaid', { scroll: false });
    state.replace.mockClear();
    fireEvent.mouseDown(screen.getByRole('tab', { name: 'Invoiced' }));
    fireEvent.click(screen.getByRole('tab', { name: 'Invoiced' }));
    expect(state.replace).toHaveBeenCalledWith('/sales/sales-and-outstanding', { scroll: false });
  });

  it('hides Invoiced and Unpaid invoices from a user with the orders permission only and opens on Delivered', () => {
    state.perms = new Set(['order_management.orders.view']);
    render(<SalesAndOutstandingView />);
    expect(screen.queryByRole('tab', { name: 'Invoiced' })).toBeNull();
    expect(screen.queryByRole('tab', { name: 'Unpaid invoices' })).toBeNull();
    expect(screen.getAllByRole('tab').map((t) => t.textContent)).toEqual(LABELS.slice(1, 5));
    expect(screen.getByTestId('report-key').textContent).toBe('sales_order_lines_ask_delivered');
  });

  it('shows Unpaid invoices alone to a finance user and opens on it', () => {
    state.perms = new Set(['finance.billing_documents.view']);
    render(<SalesAndOutstandingView />);
    expect(screen.getAllByRole('tab').map((t) => t.textContent)).toEqual(['Unpaid invoices']);
    expect(screen.getByTestId('report-key').textContent).toBe('unpaid_documents');
  });

  it('hides the five order tabs from a user with the reports permission only', () => {
    state.perms = new Set(['sales.reports.view']);
    render(<SalesAndOutstandingView />);
    expect(screen.getAllByRole('tab').map((t) => t.textContent)).toEqual(['Invoiced']);
  });

  it('a ?tab= the user may not see falls back to their first tab', () => {
    state.perms = new Set(['order_management.orders.view']);
    state.tab = 'invoiced';
    render(<SalesAndOutstandingView />);
    expect(screen.getByTestId('report-key').textContent).toBe('sales_order_lines_ask_delivered');
  });

  it('renders nothing for a user with neither permission', () => {
    state.perms = new Set();
    const { container } = render(<SalesAndOutstandingView />);
    expect(container.textContent).toBe('');
  });
});
