import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('./slaKpiService', () => ({
  getKpiSummary: vi.fn(),
  getKpiLeaderboard: vi.fn(),
  getKpiTasks: vi.fn(),
}));

import { getKpiSummary, getKpiLeaderboard, getKpiTasks } from './slaKpiService';
import Page from './page';

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <Page />
    </QueryClientProvider>,
  );
}

const SUMMARY = {
  scope: 'all', opened: 5, responded: 4, resolved: 3, escalated: 2,
  escalated_auto: 1, escalated_manual: 1, response_met: 3, response_breach: 1,
  resolution_met: 2, resolution_breach: 1, pct_response_met: 75, pct_resolution_met: 66.7,
  avg_response_time_hours: 2.5, avg_resolution_time_hours: 6, median_response_time_hours: 2,
  median_resolution_time_hours: 5,
};

describe('SLA KPI Dashboard (TCK-32 UX1)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders summary cards + leaderboard + tasks with data', async () => {
    (getKpiSummary as any).mockResolvedValue(SUMMARY);
    (getKpiLeaderboard as any).mockResolvedValue([
      { assignee_id: 'u1', assignee_name: 'Alice', total: 5, resolved: 3, avg_response_time_hours: 2.5, avg_resolution_time_hours: 6, breach_count: 1 },
    ]);
    (getKpiTasks as any).mockResolvedValue({
      total: 1,
      data: [{
        tracking_id: 't1', source_entity_type: 'complaint', source_entity_id: 'c1', current_tier: 2,
        assignee_id: 'u1', assignee_name: 'Alice', response_time_hours: 2, resolution_time_hours: null,
        is_resolved: false, response_met: true, resolution_met: false, escalations_auto: 1, escalations_manual: 1,
      }],
    });
    renderPage();
    expect(await screen.findByText('Opened')).toBeInTheDocument();
    expect(screen.getAllByText('5').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('75%')).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByText('Alice').length).toBeGreaterThanOrEqual(1));
  });

  it('renders empty states', async () => {
    (getKpiSummary as any).mockResolvedValue({ ...SUMMARY, opened: 0 });
    (getKpiLeaderboard as any).mockResolvedValue([]);
    (getKpiTasks as any).mockResolvedValue({ total: 0, data: [] });
    renderPage();
    expect(await screen.findByText('No assignees in this scope.')).toBeInTheDocument();
    expect(await screen.findByText('No tasks in this scope.')).toBeInTheDocument();
  });
});
