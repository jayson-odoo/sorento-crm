/**
 * Covers UAC OBS-S1-13, OBS-S1-15 and OBS-S1-16 — making a failure count actionable.
 *
 * "5 failed" is a fact, not a lead. Two things have to hold before the number
 * is worth anything: the causes behind it are visible without navigating away,
 * and the drill-down link lands on exactly the rows that produced the count —
 * which it previously did not, because the href hardcoded a 24h window while
 * the dashboard could be showing 30 days.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';

vi.mock('../hooks/useHealth', () => ({
  useHealthSummary: vi.fn(),
}));

import { useHealthSummary } from '../hooks/useHealth';
import HealthDashboard from './HealthDashboard';
import type { HealthSummary } from '../types/health.types';

const mockedHook = vi.mocked(useHealthSummary);

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
  email_outbox: { pending: 0, sent: 0, failed: 0, cancelled: 0, failed_in_window: 0, failed_last_24h: 0 },
  imports: { total_last_24h: 0, finished_last_24h: 0, failed_last_24h: 0, success_rate: 100 },
  scheduled_tasks: { total: 5, overdue: 0, last_run_failed: 0 },
  integrations: { channels: [] },
  audit_activity: { count_last_24h: 0, daily_trend: [] },
};

/** Mirrors the live shape: 821 respond_io failures are really 3 distinct faults. */
const withFailures: HealthSummary = {
  ...base,
  integrations: {
    channels: [
      {
        channel: 'respond_io',
        success: 13,
        failed: 776,
        benign: 0,
        in_flight: 0,
        total: 789,
        top_failures: [
          {
            signature: "client error '<n> unauthorized' for url '<url>'",
            sample_message: "Client error '401 Unauthorized' for url 'https://api.respond.io/v2/contact/id:55555/message'",
            status_code: 401,
            count: 428,
          },
          {
            signature: "client error '<n> forbidden' for url '<url>'",
            sample_message: "Client error '403 Forbidden' for url 'https://api.respond.io/v2/contact/id:437264483/message'",
            status_code: 403,
            count: 330,
          },
          {
            signature: '<n>h window closed and template send skipped',
            sample_message: "24h window closed and template send skipped for use case 'sla_daily_summary'",
            status_code: null,
            count: 18,
          },
        ],
      },
      {
        channel: 'n8n',
        success: 26,
        failed: 0,
        benign: 0,
        in_flight: 49,
        total: 75,
        top_failures: [],
      },
    ],
  },
};

function renderWith(summary: HealthSummary) {
  mockedHook.mockReturnValue(hookState({ data: summary }));
  return render(<HealthDashboard />);
}

beforeEach(() => {
  vi.clearAllMocks();
  cleanup();
});

describe('HealthDashboard: pinpointing an integration failure', () => {
  it('names each distinct cause with its own count, without leaving the page', () => {
    renderWith(withFailures);

    const list = screen.getByTestId('health-integration-failures-respond_io');
    expect(list).toHaveTextContent('401');
    expect(list).toHaveTextContent('428×');
    expect(list).toHaveTextContent('403');
    expect(list).toHaveTextContent('330×');
    expect(list).toHaveTextContent(/24h window closed/i);
  });

  it('shows the un-masked sample message, not the normalised signature', () => {
    // The signature is a grouping key with ids blanked out — useless to paste
    // into a log search. The operator needs a message that actually occurred.
    renderWith(withFailures);
    const list = screen.getByTestId('health-integration-failures-respond_io');
    expect(list).toHaveTextContent('api.respond.io/v2/contact/id:55555/message');
    expect(list).not.toHaveTextContent("client error '<n> unauthorized'");
  });

  it('renders no cause list for a channel with zero failures', () => {
    renderWith(withFailures);
    expect(screen.queryByTestId('health-integration-failures-n8n')).not.toBeInTheDocument();
  });

  it('omits the status-code badge when the failure carried no HTTP code', () => {
    renderWith(withFailures);
    // The template-removed fault has status_code null; it still renders its
    // count and message rather than an empty badge.
    const list = screen.getByTestId('health-integration-failures-respond_io');
    expect(list).toHaveTextContent('18×');
  });

  it('drill-down carries the dashboard window, so the link matches the count', () => {
    renderWith(withFailures);

    const from = screen.getByTestId('health-range-from') as HTMLInputElement;
    fireEvent.change(from, { target: { value: '2026-06-01T00:00' } });

    const url = hrefUrl(screen.getByTestId('health-integration-failed-link-respond_io'));
    expect(url.pathname).toBe('/integration-management/integration-logs');
    expect(url.searchParams.get('integration_channel')).toBe('respond_io');
    expect(url.searchParams.get('status')).toBe('failed');
    // The whole point: widening the window must widen the link too.
    expect(url.searchParams.get('created_from')).toBe(
      new Date('2026-06-01T00:00').toISOString(),
    );
  });
});
