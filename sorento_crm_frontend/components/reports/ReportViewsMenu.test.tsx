/**
 * Saved views (AC-C3, AC-C4, AC-C6).
 *
 * Two rules carry the weight here:
 *
 * - Mine is what the caller OWNS, published ones included (badged Shared); Shared is other
 *   people's published views. A view leaving its author's own list the moment they share it
 *   is how somebody loses the view they just made.
 * - Publish and Set as default are ABSENT without `reports.views.publish`, never disabled.
 *   A greyed-out control the user can never earn is only an invitation to ask why.
 *
 * The dropdown is rendered flat (the real one is a Radix popover) so the menu's CONTENT is
 * what is asserted, not popover mechanics.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render as rtlRender, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DropdownMenuContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DropdownMenuLabel: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DropdownMenuSeparator: () => <hr />,
  DropdownMenuItem: ({
    children,
    onClick,
    disabled,
  }: React.PropsWithChildren<{ onClick?: () => void; disabled?: boolean }>) => (
    <button type="button" onClick={onClick} disabled={disabled}>
      {children}
    </button>
  ),
}));

const fetchReportViews = vi.fn();
const createReportView = vi.fn();
const publishReportView = vi.fn();
const setDefaultReportView = vi.fn();
const deleteReportView = vi.fn();

vi.mock('@/services/reportService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/reportService')>();
  return {
    ...actual,
    fetchReportViews: (...a: unknown[]) => fetchReportViews(...a),
    createReportView: (...a: unknown[]) => createReportView(...a),
    publishReportView: (...a: unknown[]) => publishReportView(...a),
    setDefaultReportView: (...a: unknown[]) => setDefaultReportView(...a),
    deleteReportView: (...a: unknown[]) => deleteReportView(...a),
  };
});

import { ReportViewsMenu } from './ReportViewsMenu';
import type { ReportView, ReportViewConfig } from '@/services/reportService';

const CONFIG: ReportViewConfig = {
  params: { date_basis: 'approved_at', period: { kind: 'year', year: 2026 }, status: ['approved'] },
  detail: { columns: ['request_number'], order: ['request_number'] },
  pivot: { rows: 'sales_agent', cols: 'month', measures: ['project_value'] },
};

const MINE_PRIVATE: ReportView = {
  id: 'v-private',
  name: 'My pipeline',
  is_shared: false,
  is_default: false,
  owner_name: 'You',
  view: CONFIG,
};

const MINE_PUBLISHED: ReportView = {
  id: 'v-published',
  name: 'Sponsorships by subject',
  is_shared: true,
  is_default: false,
  owner_name: 'You',
  view: CONFIG,
};

const THEIRS: ReportView = {
  id: 'v-theirs',
  name: 'Management default',
  is_shared: true,
  is_default: true,
  owner_name: 'Chin Wei Loon',
  view: CONFIG,
};

function render(props: Partial<React.ComponentProps<typeof ReportViewsMenu>> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onApply = vi.fn();
  const utils = rtlRender(
    <QueryClientProvider client={client}>
      <ReportViewsMenu
        reportKey="sponsorship"
        canPublish
        currentViewId={null}
        currentConfig={CONFIG}
        onApply={onApply}
        {...props}
      />
    </QueryClientProvider>,
  );
  return { ...utils, onApply };
}

beforeEach(() => {
  vi.clearAllMocks();
  fetchReportViews.mockResolvedValue({ mine: [MINE_PRIVATE, MINE_PUBLISHED], shared: [THEIRS] });
  Element.prototype.scrollIntoView = vi.fn();
  Element.prototype.hasPointerCapture = vi.fn();
});

describe('ReportViewsMenu', () => {
  it('lists Mine and Shared, and keeps a published view under Mine', async () => {
    render();

    expect(await screen.findByText('My pipeline')).toBeInTheDocument();
    expect(screen.getByText('Sponsorships by subject')).toBeInTheDocument();
    expect(screen.getByText('Management default')).toBeInTheDocument();
    // The author's own published view is badged rather than moved: the section heading
    // "Shared" plus the badge on that view make two.
    expect(screen.getAllByText('Shared')).toHaveLength(2);
    expect(screen.getByText('Default')).toBeInTheDocument();
  });

  it('says so when there is nothing saved yet', async () => {
    fetchReportViews.mockResolvedValue({ mine: [], shared: [] });
    render();

    expect(await screen.findByText('No saved views yet')).toBeInTheDocument();
    expect(screen.getByText('No shared views yet')).toBeInTheDocument();
  });

  it('applies the view the user picks', async () => {
    const { onApply } = render();

    fireEvent.click(await screen.findByText('My pipeline'));

    expect(onApply).toHaveBeenCalledWith(MINE_PRIVATE);
  });

  it('Report default resets to the report own default', async () => {
    const { onApply } = render({ currentViewId: 'v-private' });

    fireEvent.click(await screen.findByText('Report default'));

    expect(onApply).toHaveBeenCalledWith(null);
  });

  it('saves the current shape under a name', async () => {
    createReportView.mockResolvedValue({ ...MINE_PRIVATE, name: 'Q3 review' });
    render();

    fireEvent.click(screen.getByRole('button', { name: 'Save view' }));
    fireEvent.change(await screen.findByLabelText('Name'), { target: { value: 'Q3 review' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(createReportView).toHaveBeenCalledWith('sponsorship', {
        name: 'Q3 review',
        view: CONFIG,
      }),
    );
  });

  it('offers Publish on an unshared view of mine when I may publish', async () => {
    publishReportView.mockResolvedValue({ ...MINE_PRIVATE, is_shared: true });
    render({ currentViewId: 'v-private' });

    fireEvent.click(await screen.findByText('Publish as shared'));

    await waitFor(() => expect(publishReportView).toHaveBeenCalledWith('sponsorship', 'v-private', true));
  });

  it('offers Set as default on an already shared view', async () => {
    setDefaultReportView.mockResolvedValue({ ...MINE_PUBLISHED, is_default: true });
    render({ currentViewId: 'v-published' });

    fireEvent.click(await screen.findByText('Set as default for everyone'));

    await waitFor(() => expect(setDefaultReportView).toHaveBeenCalledWith('sponsorship', 'v-published'));
  });

  it('hides both publishing actions entirely without the permission', async () => {
    render({ canPublish: false, currentViewId: 'v-private' });

    // The list still loads, so absence here is a decision and not a race. The name is on
    // the trigger as well as in the menu, hence getAllByText.
    await waitFor(() => expect(screen.getAllByText('My pipeline').length).toBeGreaterThan(1));
    expect(screen.queryByText('Publish as shared')).not.toBeInTheDocument();
    expect(screen.queryByText('Set as default for everyone')).not.toBeInTheDocument();
  });

  it('confirms before deleting a view, and never uses a bare confirm()', async () => {
    render({ currentViewId: 'v-private' });

    fireEvent.click(await screen.findByText('Delete view'));

    expect(await screen.findByText(/Delete "My pipeline"\? This cannot be undone\./)).toBeInTheDocument();
    expect(deleteReportView).not.toHaveBeenCalled();
  });

  it('does not offer to delete somebody else published view', async () => {
    render({ currentViewId: 'v-theirs' });

    await waitFor(() => expect(screen.getAllByText('Management default').length).toBeGreaterThan(1));
    expect(screen.queryByText('Delete view')).not.toBeInTheDocument();
  });
});
