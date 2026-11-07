/**
 * NPA-FROM-SI, owner hand test 7 Nov ("supposed to be tgt"): the stock inquiry page has ONE tab
 * bar. "New product applications (N)" is an extra tab of the page's FormDetailTabsWithRevisions
 * (Details / Comments / Revisions / SLA Tracking), not a second row inside the detail.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';

type ExtraTab = { value: string; label: string; content: ReactNode };
const captured: { extraTabs?: ExtraTab[] } = {};

vi.mock('@/app/(protected)/sla-management/_shared/FormDetailTabsWithRevisions', () => ({
  __esModule: true,
  default: ({ extraTabs = [], children }: { extraTabs?: ExtraTab[]; children: ReactNode }) => {
    captured.extraTabs = extraTabs;
    return (
      <div>
        <div role="tablist">
          <button type="button" role="tab">Details</button>
          {extraTabs.map((t) => (
            <button key={t.value} type="button" role="tab">{t.label}</button>
          ))}
        </div>
        <div data-testid="details">{children}</div>
        {extraTabs.map((t) => (
          <div key={t.value} data-testid={`panel-${t.value}`}>{t.content}</div>
        ))}
      </div>
    );
  },
}));

let permissionMap: Record<string, boolean> = {};
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => permissionMap[slug] ?? false,
}));

const applications: { data: unknown[] | undefined; isError: boolean } = { data: [], isError: false };
vi.mock('../../new-product-applications/hooks/useNewProductApplications', () => ({
  useStockInquiryApplicationsQuery: (_id: string | null, enabled: boolean) => ({
    data: enabled && !applications.isError ? applications.data : undefined,
    isError: enabled && applications.isError,
  }),
}));

import StockInquiryDetailTabs from './StockInquiryDetailTabs';

const VIEW = 'procurement.new_product_applications.view';

const renderTabs = () =>
  render(
    <StockInquiryDetailTabs inquiryId="si-1">
      <p>the form</p>
    </StockInquiryDetailTabs>,
  );

describe('StockInquiryDetailTabs', () => {
  beforeEach(() => {
    permissionMap = {};
    applications.data = [];
    applications.isError = false;
    captured.extraTabs = undefined;
  });

  it('puts New product applications (N) in the ONE page tab bar, next to Details', () => {
    permissionMap = { [VIEW]: true };
    renderTabs();
    expect(screen.getAllByRole('tablist')).toHaveLength(1);
    const names = screen.getAllByRole('tab').map((t) => t.textContent);
    expect(names).toEqual(['Details', 'New product applications (0)']);
    expect(screen.getByTestId('details')).toHaveTextContent('the form');
  });

  it('counts the applications and lists them (number links to the application)', () => {
    permissionMap = { [VIEW]: true };
    applications.data = [
      {
        id: 'a-1',
        application_no: 'NPA-000001',
        status: 'completed',
        status_label: 'Completed',
        created_at: '2026-11-03T02:00:00',
        opened_codes: [],
        created_codes: [
          { product_code: 'XY-1234-MB-69', current_codes: ['XY-1234-MB'], created_at: '2026-11-03T02:00:00' },
        ],
      },
    ];
    renderTabs();
    expect(screen.getByRole('tab', { name: 'New product applications (1)' })).toBeInTheDocument();
    const link = screen.getByRole('link', { name: 'NPA-000001' });
    expect(link).toHaveAttribute('href', '/procurement-management/new-product-applications/a-1');
    expect(screen.getByText('XY-1234-MB -> XY-1234-MB-69')).toBeInTheDocument();
  });

  it('shows the empty state in the tab when nothing was raised', () => {
    permissionMap = { [VIEW]: true };
    renderTabs();
    expect(screen.getByTestId('panel-applications')).toHaveTextContent('No new product applications');
    expect(screen.getByTestId('panel-applications')).toHaveTextContent(
      'Applications created from this inquiry show here.',
    );
  });

  it('adds no tab for a user with no new product application permission', () => {
    renderTabs();
    expect(captured.extraTabs).toEqual([]);
    expect(screen.queryByRole('tab', { name: /new product applications/i })).toBeNull();
  });

  it('a failed list shows an error in the tab, not (0) and the empty state', () => {
    permissionMap = { [VIEW]: true };
    applications.isError = true;
    renderTabs();
    expect(screen.getByRole('tab', { name: 'New product applications' })).toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: /\(0\)/ })).toBeNull();
    const panel = screen.getByTestId('panel-applications');
    expect(panel).toHaveTextContent('Could not load the new product applications.');
    expect(panel).not.toHaveTextContent('No new product applications');
  });
});
