/**
 * SimulationPlanningTab - the sim page's "Planning view" tab. Renders the REAL
 * reorder PlanLinesSection scoped to whichever run `useTodayRun` resolves against
 * THIS backend, gated on `simDbActive` so it never shows the real dev-DB plan
 * through a backend that is not actually pointed at the sim database.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';

const useTodayRun = vi.fn();
vi.mock('../../reorder/hooks/useReorderRun', () => ({ useTodayRun: () => useTodayRun() }));

vi.mock('../../reorder/components/PlanLinesSection', () => ({
  PlanLinesSection: ({ runId }: { runId: string | null }) => <div>plan-lines-section runId={runId}</div>,
}));

import { SimulationPlanningTab } from './SimulationPlanningTab';

beforeEach(() => {
  useTodayRun.mockReset();
});

describe('SimulationPlanningTab - gated on sim_db_active', () => {
  it('shows the CTA with the serve command when the backend is not on the sim database', () => {
    useTodayRun.mockReturnValue({ data: null, isLoading: false, isError: false, error: null });
    render(<SimulationPlanningTab simDbActive={false} />);

    expect(
      screen.getByText(/the planning view needs the backend on the sim database/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/scm_sim serve/)).toBeInTheDocument();
    expect(screen.queryByText(/plan-lines-section/)).not.toBeInTheDocument();
  });

  it('never fetches or renders the real grid while not on the sim database', () => {
    useTodayRun.mockReturnValue({ data: { run_id: 'run-real' }, isLoading: false, isError: false, error: null });
    render(<SimulationPlanningTab simDbActive={false} />);

    expect(screen.queryByText(/runId=run-real/)).not.toBeInTheDocument();
  });
});

describe('SimulationPlanningTab - active sim backend', () => {
  it('renders a loading state while the run resolves', () => {
    useTodayRun.mockReturnValue({ data: undefined, isLoading: true, isError: false, error: null });
    render(<SimulationPlanningTab simDbActive />);

    expect(screen.queryByText(/plan-lines-section/)).not.toBeInTheDocument();
    expect(screen.queryByText(/no sim run yet/i)).not.toBeInTheDocument();
  });

  it('renders an error state when the run resolution fails', () => {
    useTodayRun.mockReturnValue({ data: null, isLoading: false, isError: true, error: new Error('boom') });
    render(<SimulationPlanningTab simDbActive />);

    expect(screen.getByText('boom')).toBeInTheDocument();
  });

  it('says there is no sim run yet when none exists', () => {
    useTodayRun.mockReturnValue({ data: null, isLoading: false, isError: false, error: null });
    render(<SimulationPlanningTab simDbActive />);

    expect(screen.getByText(/no sim run yet/i)).toBeInTheDocument();
  });

  it('renders the real PlanLinesSection scoped to the resolved run', () => {
    useTodayRun.mockReturnValue({
      data: { run_id: 'run-sim-1', is_today: true, in_progress: false },
      isLoading: false,
      isError: false,
      error: null,
    });
    render(<SimulationPlanningTab simDbActive />);

    expect(screen.getByText(/plan-lines-section runId=run-sim-1/)).toBeInTheDocument();
  });
});
