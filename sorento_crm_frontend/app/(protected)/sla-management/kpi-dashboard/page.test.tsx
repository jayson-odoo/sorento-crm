import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// jsdom polyfills required by ScrollArea / DataGrid.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as any).ResizeObserver = ResizeObserverStub;
if (!window.matchMedia) {
  (window as any).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}

vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('next/navigation', () => ({
  usePathname: () => '/sla-management/kpi-dashboard',
  useRouter: () => ({ push: vi.fn() }),
}));

// Default: user can view. Overridden per-test for the denial case.
const hasPermission = vi.fn(() => true);
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => hasPermission(),
}));

// DataGrid persists column prefs via this hook (fires network) - stub it.
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

vi.mock('./slaKpiService', () => ({
  getKpiSummary: vi.fn(),
  getKpiTrend: vi.fn(),
  getKpiTasks: vi.fn(),
}));

import { getKpiSummary, getKpiTrend, getKpiTasks } from './slaKpiService';
import Page from './page';
import { SLAKpiDashboardContent } from './SLAKpiDashboardContent';

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <Page />
    </QueryClientProvider>,
  );
}

function renderContent(props?: { defaultWindowDays?: number }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SLAKpiDashboardContent {...props} />
    </QueryClientProvider>,
  );
}

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

const SUMMARY = {
  scope: 'all', opened: 5, responded: 4, resolved: 3,
  stage_pending: 1, stage_responded_open: 1, stage_resolved: 3,
  pct_stage_pending: 20, pct_stage_responded_open: 20, pct_stage_resolved: 60,
  responded_within: 3, responded_overdue: 1, resolved_within: 2, resolved_overdue: 1,
  pct_responded_within: 75, pct_resolved_within: 66.7,
  pending_within: 1, pending_overdue: 0, responded_open_within: 0, responded_open_overdue: 1,
  pct_pending_within: 100, pct_responded_open_within: 0,
  escalated: 2,
  escalated_auto: 1, escalated_manual: 1, response_met: 3, response_breach: 1,
  resolution_met: 2, resolution_breach: 1, pct_response_met: 75, pct_resolution_met: 66.7,
  avg_response_time_hours: 2.5, avg_resolution_time_hours: 6, median_response_time_hours: 2,
  median_resolution_time_hours: 5,
};

describe('SLA KPI Dashboard (TCK-32 UX1)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    hasPermission.mockReturnValue(true);
  });

  it('renders stage/timeliness cards + tasks with data', async () => {
    (getKpiSummary as any).mockResolvedValue(SUMMARY);
    (getKpiTrend as any).mockResolvedValue([]);
    (getKpiTasks as any).mockResolvedValue({
      total: 1,
      data: [{
        tracking_id: 't1', source_entity_type: 'complaint', source_entity_id: 'c1', current_tier: 2,
        current_tier_started_at: '2026-06-20T01:00:00', response_due: '2026-06-21T01:00:00', resolution_due: null,
        assignee_id: 'u1', assignee_name: 'Alice', response_time_hours: 2, resolution_time_hours: null,
        is_resolved: false, response_met: true, resolution_met: false, escalations_auto: 1, escalations_manual: 1,
      }],
    });
    renderPage();
    expect(await screen.findByText('Stage breakdown')).toBeInTheDocument();
    expect(screen.getAllByText('75%').length).toBeGreaterThanOrEqual(1);
    // Owner name resolved in the tasks grid (no UUID).
    await waitFor(() => expect(screen.getAllByText('Alice').length).toBeGreaterThanOrEqual(1));
  });

  it('renders empty states', async () => {
    (getKpiSummary as any).mockResolvedValue({ ...SUMMARY, opened: 0 });
    (getKpiTrend as any).mockResolvedValue([]);
    (getKpiTasks as any).mockResolvedValue({ total: 0, data: [] });
    renderPage();
    expect(await screen.findByText('No tasks in this scope.')).toBeInTheDocument();
    expect(await screen.findByText('No trend data for this scope.')).toBeInTheDocument();
  });

  it('hides content when the user lacks sla.kpi.view', async () => {
    hasPermission.mockReturnValue(false);
    renderPage();
    expect(await screen.findByText(/don.t have access/i)).toBeInTheDocument();
    expect(getKpiSummary).not.toHaveBeenCalled();
  });

  it('passes a bounded date window to all three queries when defaultWindowDays is set', async () => {
    (getKpiSummary as any).mockResolvedValue(SUMMARY);
    (getKpiTrend as any).mockResolvedValue([]);
    (getKpiTasks as any).mockResolvedValue({ total: 0, data: [] });
    renderContent({ defaultWindowDays: 30 });

    // Scoped label is surfaced so users know the embed is windowed.
    expect(await screen.findByText('Last 30 days')).toBeInTheDocument();

    await waitFor(() => expect(getKpiSummary).toHaveBeenCalled());
    const summaryWindow = (getKpiSummary as any).mock.calls[0][1];
    expect(summaryWindow.date_from).toMatch(ISO_DATE);
    expect(summaryWindow.date_to).toMatch(ISO_DATE);
    // 30-day span (inclusive of today's date_to).
    expect(summaryWindow.date_from < summaryWindow.date_to).toBe(true);

    await waitFor(() => expect(getKpiTrend).toHaveBeenCalled());
    expect((getKpiTrend as any).mock.calls[0][1]).toEqual(summaryWindow);

    await waitFor(() => expect(getKpiTasks).toHaveBeenCalled());
    // getKpiTasks(scope, pagination, sorting, view, state, window) - window is arg 6.
    expect((getKpiTasks as any).mock.calls[0][5]).toEqual(summaryWindow);
  });

  it('omits the date window (all-time) when defaultWindowDays is unset', async () => {
    (getKpiSummary as any).mockResolvedValue(SUMMARY);
    (getKpiTrend as any).mockResolvedValue([]);
    (getKpiTasks as any).mockResolvedValue({ total: 0, data: [] });
    renderContent();

    expect(screen.queryByText(/Last \d+ days/)).not.toBeInTheDocument();

    await waitFor(() => expect(getKpiSummary).toHaveBeenCalled());
    expect((getKpiSummary as any).mock.calls[0][1]).toBeUndefined();

    await waitFor(() => expect(getKpiTrend).toHaveBeenCalled());
    expect((getKpiTrend as any).mock.calls[0][1]).toBeUndefined();

    await waitFor(() => expect(getKpiTasks).toHaveBeenCalled());
    expect((getKpiTasks as any).mock.calls[0][5]).toBeUndefined();
  });
});
