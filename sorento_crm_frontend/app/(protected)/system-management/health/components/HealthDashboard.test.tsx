import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('../hooks/useHealth', () => ({
  useHealthSummary: vi.fn(),
}));

import { useHealthSummary } from '../hooks/useHealth';
import HealthDashboard from './HealthDashboard';
import type { HealthSummary } from '../types/health.types';

const mockedHook = vi.mocked(useHealthSummary);

const fullSummary: HealthSummary = {
  generated_at: '2026-06-30T12:00:00Z',
  email_outbox: { pending: 3, sent: 10, failed: 2, cancelled: 1, failed_last_24h: 2 },
  imports: { total_last_24h: 4, finished_last_24h: 3, failed_last_24h: 1, success_rate: 75 },
  scheduled_tasks: { total: 5, overdue: 1, last_run_failed: 0 },
  integrations: {
    channels: [{ channel: 'respond_io', success: 8, failed: 1, total: 9 }],
  },
  audit_activity: {
    count_last_24h: 12,
    daily_trend: [{ date: '2026-06-30', count: 12 }],
  },
};

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

beforeEach(() => vi.clearAllMocks());

describe('HealthDashboard', () => {
  it('renders loading skeletons while loading', () => {
    mockedHook.mockReturnValue(hookState({ isLoading: true }));
    render(<HealthDashboard />);
    expect(screen.getByRole('status', { name: /loading system health/i })).toBeInTheDocument();
  });

  it('renders every metric card with data', () => {
    mockedHook.mockReturnValue(hookState({ data: fullSummary }));
    render(<HealthDashboard />);

    expect(screen.getByText('Email Queue')).toBeInTheDocument();
    expect(screen.getByText('Imports (24h)')).toBeInTheDocument();
    expect(screen.getByText('Scheduled Tasks')).toBeInTheDocument();
    expect(screen.getByText('Integrations (24h)')).toBeInTheDocument();
    expect(screen.getByText('Audit Activity')).toBeInTheDocument();
    // warning badge for failed emails in the last 24h
    expect(screen.getByText(/2 failed \/ 24h/i)).toBeInTheDocument();
    // integration channel row
    expect(screen.getByText('respond_io')).toBeInTheDocument();
  });

  it('renders empty state for a null metric block', () => {
    mockedHook.mockReturnValue(
      hookState({ data: { ...fullSummary, integrations: null } }),
    );
    render(<HealthDashboard />);
    expect(screen.getByText(/integration logs not available/i)).toBeInTheDocument();
  });

  it('renders an error card with a retry button that refetches', () => {
    const refetch = vi.fn();
    mockedHook.mockReturnValue(
      hookState({ isError: true, error: new Error('Boom'), refetch }),
    );
    render(<HealthDashboard />);

    expect(screen.getByText(/unable to load system health/i)).toBeInTheDocument();
    expect(screen.getByText('Boom')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /retry/i }));
    expect(refetch).toHaveBeenCalledTimes(1);
  });
});
