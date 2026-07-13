import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';

vi.mock('../hooks/useHealth', () => ({
  useHealthSummary: vi.fn(),
}));

import { useHealthSummary } from '../hooks/useHealth';
import HealthDashboard from './HealthDashboard';
import type { HealthSummary } from '../types/health.types';

const mockedHook = vi.mocked(useHealthSummary);

/** Parse an <a href> (possibly relative) into a URL for structured param assertions. */
function hrefUrl(el: HTMLElement): URL {
  return new URL(el.getAttribute('href') || '', 'http://localhost');
}

function hookState(overrides: Record<string, unknown>) {
  return {
    data: undefined,
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    ...overrides,
  } as unknown as ReturnType<typeof useHealthSummary>;
}

const base: HealthSummary = {
  generated_at: '2026-06-30T12:00:00Z',
  email_outbox: { pending: 0, sent: 0, failed: 0, cancelled: 0, failed_last_24h: 0 },
  imports: { total_last_24h: 0, finished_last_24h: 0, failed_last_24h: 0, success_rate: 100 },
  scheduled_tasks: { total: 5, overdue: 0, last_run_failed: 0 },
  integrations: { channels: [] },
  audit_activity: { count_last_24h: 0, daily_trend: [] },
};

function renderWith(summary: HealthSummary) {
  mockedHook.mockReturnValue(hookState({ data: summary }));
  return render(<HealthDashboard />);
}

beforeEach(() => {
  vi.clearAllMocks();
  cleanup();
});

describe('HealthDashboard drill-down: Audit Activity day bars', () => {
  it('each trend day renders a link scoping the whole UTC calendar day on /audit-logs', () => {
    renderWith({
      ...base,
      audit_activity: {
        count_last_24h: 20,
        daily_trend: [
          { date: '2026-06-29', count: 8 },
          { date: '2026-06-30', count: 12 },
        ],
      },
    });

    const link = screen.getByTestId('health-audit-day-link-2026-06-30');
    const url = hrefUrl(link);
    expect(url.pathname).toBe('/system-management/audit-logs');
    expect(url.searchParams.get('changed_from')).toBe('2026-06-30T00:00:00.000Z');
    expect(url.searchParams.get('changed_to')).toBe('2026-06-30T23:59:59.999Z');

    // the other day bar links to its own day, not the same one
    const other = hrefUrl(screen.getByTestId('health-audit-day-link-2026-06-29'));
    expect(other.searchParams.get('changed_from')).toBe('2026-06-29T00:00:00.000Z');
    expect(other.searchParams.get('changed_to')).toBe('2026-06-29T23:59:59.999Z');
  });

  it('renders an empty state (no day links) when the trend is empty', () => {
    renderWith({ ...base, audit_activity: { count_last_24h: 0, daily_trend: [] } });
    expect(screen.getByText(/no audit activity recorded/i)).toBeInTheDocument();
    expect(screen.queryByTestId(/health-audit-day-link-/)).not.toBeInTheDocument();
  });
});

describe('HealthDashboard drill-down: Integration failed counts', () => {
  it('links a channel failed count to /integration-logs filtered to that channel + failed + last 24h ONLY when failed > 0', () => {
    renderWith({
      ...base,
      integrations: {
        channels: [
          { channel: 'respond_io', success: 8, failed: 3, total: 11 },
          { channel: 'n8n', success: 5, failed: 0, total: 5 },
        ],
      },
    });

    // failed > 0 -> link present with the right params
    const link = screen.getByTestId('health-integration-failed-link-respond_io');
    const url = hrefUrl(link);
    expect(url.pathname).toBe('/integration-management/integration-logs');
    expect(url.searchParams.get('integration_channel')).toBe('respond_io');
    expect(url.searchParams.get('status')).toBe('failed');
    // created_from is a last-24h ISO lower bound
    const createdFrom = url.searchParams.get('created_from');
    expect(createdFrom).toBeTruthy();
    expect(() => new Date(createdFrom as string).toISOString()).not.toThrow();
    expect(link.textContent).toBe('3');

    // failed == 0 -> NO link (plain number rendered)
    expect(screen.queryByTestId('health-integration-failed-link-n8n')).not.toBeInTheDocument();
  });

  it('renders an empty state when there is no integration activity', () => {
    renderWith({ ...base, integrations: { channels: [] } });
    expect(screen.getByText(/no integration activity in the last 24 hours/i)).toBeInTheDocument();
  });
});

describe('HealthDashboard drill-down: Scheduled Tasks counts', () => {
  it('links overdue count to scheduled-tasks only when overdue > 0', () => {
    renderWith({
      ...base,
      scheduled_tasks: { total: 5, overdue: 2, last_run_failed: 0 },
    });

    const overdue = screen.getByTestId('health-scheduled-overdue-link');
    expect(overdue.getAttribute('href')).toBe('/system-management/scheduled-tasks');
    expect(overdue.textContent).toBe('2');
    // last_run_failed == 0 -> no failed link
    expect(screen.queryByTestId('health-scheduled-failed-link')).not.toBeInTheDocument();
  });

  it('links last-run-failed count to scheduled-tasks only when > 0', () => {
    renderWith({
      ...base,
      scheduled_tasks: { total: 5, overdue: 0, last_run_failed: 4 },
    });

    const failed = screen.getByTestId('health-scheduled-failed-link');
    expect(failed.getAttribute('href')).toBe('/system-management/scheduled-tasks');
    expect(failed.textContent).toBe('4');
    // overdue == 0 -> no overdue link
    expect(screen.queryByTestId('health-scheduled-overdue-link')).not.toBeInTheDocument();
  });

  it('renders no scheduled-task links when both counts are zero', () => {
    renderWith({ ...base, scheduled_tasks: { total: 5, overdue: 0, last_run_failed: 0 } });
    expect(screen.queryByTestId('health-scheduled-overdue-link')).not.toBeInTheDocument();
    expect(screen.queryByTestId('health-scheduled-failed-link')).not.toBeInTheDocument();
  });
});
