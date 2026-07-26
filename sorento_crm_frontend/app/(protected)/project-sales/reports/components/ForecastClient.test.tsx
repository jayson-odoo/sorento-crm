/**
 * S5a - ForecastClient (AC-I1, AC-I2a, AC-I4).
 *
 * What is pinned here is the SEPARATION, because that is the design: Committed on its own,
 * Pipeline and Weighted together under a "Speculative / Not revenue" label, and no total
 * anywhere. A future refactor that helpfully adds a "Total forecast" card would pass a
 * data-shape test and destroy the point of the page, so the absence is asserted.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ProjectDashboard } from '../../_shared/types/project.types';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

const getProjectDashboard = vi.fn();

vi.mock('../../_shared/services/projectService', async (importOriginal) => {
  const actual = await importOriginal<
    typeof import('../../_shared/services/projectService')
  >();
  return {
    ...actual,
    getProjectDashboard: (...args: unknown[]) => getProjectDashboard(...args),
  };
});

import { ForecastClient } from './ForecastClient';

function dashboard(overrides: Partial<ProjectDashboard> = {}): ProjectDashboard {
  return {
    forecast: {
      pipeline: '120000.00',
      weighted: '48000.00',
      committed: '75000.00',
      project_count: 4,
      // Split across two years so no year row repeats a headline figure. "Committed" itself
      // legitimately appears three times (card title plus two table headers), so the assertions
      // below lean on the unique money strings and the unique copy, not on the bare label.
      by_year: [
        { year: 2028, pipeline: '70000.00', weighted: '28000.00', committed: '45000.00' },
        { year: 2029, pipeline: '50000.00', weighted: '20000.00', committed: '30000.00' },
      ],
      undated: { pipeline: '0.00', weighted: '0.00', committed: '0.00' },
      ...(overrides.forecast ?? {}),
    },
    conversion: { won: 2, lost: 1, decided: 3, open: 1, rate: '66.67', ...(overrides.conversion ?? {}) },
    loss_reasons: overrides.loss_reasons ?? [{ reason: 'price', label: 'Price', count: 1 }],
    by_salesperson:
      overrides.by_salesperson ?? [
        {
          owner_user_id: 'u1',
          owner_name: 'Ali',
          project_count: 3,
          pipeline: '91000.00',
          weighted: '36400.00',
          committed: '61000.00',
        },
      ],
    sponsorship:
      overrides.sponsorship ?? {
        sponsored_projects: 2,
        converted_projects: 1,
        rate: '50.00',
        sponsored_spend: '4000.00',
      },
    delivery_lag_months: overrides.delivery_lag_months ?? 30,
  };
}

function renderPage(data: ProjectDashboard | null) {
  getProjectDashboard.mockResolvedValue(data ?? dashboard());
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <ForecastClient />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('ForecastClient', () => {
  it('keeps the three numbers apart and labels the speculative pair', async () => {
    renderPage(dashboard());

    expect(await screen.findByText(/The only one of the three that is banked/i)).toBeInTheDocument();
    expect(screen.getByText('Speculative')).toBeInTheDocument();
    expect(screen.getByText('Not revenue')).toBeInTheDocument();
    expect(screen.getByText('RM 75,000.00')).toBeInTheDocument();
    expect(screen.getByText('RM 120,000.00')).toBeInTheDocument();
    expect(screen.getByText('RM 48,000.00')).toBeInTheDocument();
  });

  it('reports no total anywhere, which is the whole point of AC-I1', async () => {
    renderPage(dashboard());

    await screen.findByText('Speculative');
    expect(screen.queryByText(/total forecast/i)).toBeNull();
    // 120,000 + 48,000 + 75,000 = 243,000. If a blended figure ever appears, it fails here.
    expect(screen.queryByText('RM 243,000.00')).toBeNull();
  });

  it('states the assumption behind the year buckets', async () => {
    renderPage(dashboard({ delivery_lag_months: 24 }));

    expect(
      await screen.findByText(/Launch date plus 24 months/i),
    ).toBeInTheDocument();
  });

  it('shows undated money as its own row rather than dropping it', async () => {
    renderPage(
      dashboard({
        forecast: {
          pipeline: '5000.00',
          weighted: '0.00',
          committed: '0.00',
          project_count: 1,
          by_year: [],
          undated: { pipeline: '5000.00', weighted: '0.00', committed: '0.00' },
        },
      }),
    );

    expect(await screen.findByText(/No project has a launch date/i)).toBeInTheDocument();
  });

  it('says "nothing decided yet" rather than 0% conversion', async () => {
    renderPage(
      dashboard({ conversion: { won: 0, lost: 0, decided: 0, open: 4, rate: null } }),
    );

    expect(await screen.findByText(/Nothing decided yet/i)).toBeInTheDocument();
    expect(screen.queryByText('0.0%')).toBeNull();
  });

  it('explains the empty state in terms of what to do next', async () => {
    renderPage(
      dashboard({
        forecast: {
          pipeline: '0.00',
          weighted: '0.00',
          committed: '0.00',
          project_count: 0,
          by_year: [],
          undated: { pipeline: '0.00', weighted: '0.00', committed: '0.00' },
        },
      }),
    );

    expect(await screen.findByText(/Nothing to forecast yet/i)).toBeInTheDocument();
    expect(screen.getByText(/Register a project/i)).toBeInTheDocument();
  });

  it('surfaces sponsorship spend against POs won', async () => {
    renderPage(dashboard());

    expect(
      await screen.findByText(/RM 4,000.00 across 2 projects, 1 of which received a PO/i),
    ).toBeInTheDocument();
  });
});
