import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within, waitFor } from '@testing-library/react';

// The DataGrid inside ScenariosGrid fetches through react-query for listing
// personalization - mock it, same as every other grid test in this app.
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('next/navigation', () => ({
  usePathname: () => '/scm/simulation',
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

const hooks = vi.hoisted(() => ({
  useSimulationOverview: vi.fn(),
  useScenarios: vi.fn(),
  useRunSimulation: vi.fn(),
  useBlessBaseline: vi.fn(),
  useScenarioDiff: vi.fn(),
}));
vi.mock('../hooks/useSimulation', () => hooks);

// The Planning view tab renders the REAL reorder grid via its own subject component
// (SimulationPlanningTab.test.tsx). Stubbed here so this file asserts tab orchestration
// only - which tab is shown, and that the gate flag reaches it - not the grid's internals.
vi.mock('./SimulationPlanningTab', () => ({
  SimulationPlanningTab: ({ simDbActive }: { simDbActive: boolean }) => (
    <div>planning-tab simDbActive={String(simDbActive)}</div>
  ),
}));

import { SimulationView } from './SimulationView';

const IDLE_MUTATION = { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false };

function overview(over: Partial<Record<string, unknown>> = {}) {
  return {
    isLoading: false,
    isSuccess: true,
    data: {
      sim_db_active: true,
      baseline_exists: true,
      baseline_blessed_at: '2026-08-01T00:00:00+00:00',
      current_exists: true,
      current_run_at: '2026-08-02T00:00:00+00:00',
      latest_run_id: 'run-1',
      scenario_count: 2,
      ...over,
    },
  };
}

function scenariosQuery(rows: unknown[], over: Partial<Record<string, unknown>> = {}) {
  return {
    data: rows,
    isLoading: false,
    isSuccess: true,
    isError: false,
    error: null,
    refetch: vi.fn(),
    ...over,
  };
}

function row(over: Partial<Record<string, unknown>> = {}) {
  return {
    code: 'SIM-P001',
    title: 'Steady high demand, low stock',
    segment: 'dealer',
    policy: 'forecast',
    expected_note: 'net (100) well below ROP (740) -> triggered buy.',
    inputs: { on_hand: 100, committed: 0, spo_incoming: 0, po_open: 0, demand_label: 'SO' },
    current: {
      rec_type: 'buy',
      recommended_qty: 1240,
      rounded_qty: 1240,
      triggered_reason: 'net_below_rop',
      cash_impact: 74400,
    },
    baseline: {
      rec_type: 'buy',
      recommended_qty: 1240,
      rounded_qty: 1240,
      triggered_reason: 'net_below_rop',
      cash_impact: 74400,
    },
    status: 'SAME',
    changed_groups: [],
    ...over,
  };
}

beforeEach(() => {
  hooks.useSimulationOverview.mockReset();
  hooks.useScenarios.mockReset();
  hooks.useRunSimulation.mockReset();
  hooks.useBlessBaseline.mockReset();
  hooks.useScenarioDiff.mockReset();
  hooks.useRunSimulation.mockReturnValue(IDLE_MUTATION);
  hooks.useBlessBaseline.mockReturnValue(IDLE_MUTATION);
  hooks.useScenarioDiff.mockReturnValue({ data: undefined, isLoading: false, isError: false, error: null });
});

describe('SimulationView - loading', () => {
  it('renders a skeleton for the overview strip while it loads', () => {
    hooks.useSimulationOverview.mockReturnValue({ isLoading: true, isSuccess: false, data: undefined });
    hooks.useScenarios.mockReturnValue(
      scenariosQuery([], { isLoading: true, isSuccess: false, data: undefined }),
    );
    render(<SimulationView />);
    // The grid itself is also loading - its own skeleton.
    expect(screen.getByTestId('scenarios-grid-loading')).toBeTruthy();
  });
});

describe('SimulationView - empty (no baseline, no run ever)', () => {
  it('shows the "run then bless" CTA instead of the grid', () => {
    hooks.useSimulationOverview.mockReturnValue(
      overview({ sim_db_active: true, baseline_exists: false, current_exists: false, baseline_blessed_at: null, current_run_at: null }),
    );
    hooks.useScenarios.mockReturnValue(scenariosQuery([]));
    render(<SimulationView />);
    expect(screen.getByText(/no run has ever been blessed as a baseline/i)).toBeTruthy();
    expect(screen.queryByRole('table')).toBeNull();
  });
});

describe('SimulationView - data', () => {
  it('renders the sim-db badge, dates, chips and the scenario grid', () => {
    hooks.useSimulationOverview.mockReturnValue(overview());
    hooks.useScenarios.mockReturnValue(scenariosQuery([row(), row({ code: 'SIM-P002', status: 'CHANGED', changed_groups: ['quantity suggestion'] })]));
    render(<SimulationView />);

    expect(screen.getByText('Sim DB')).toBeTruthy();
    expect(screen.getByText(/1 same/)).toBeTruthy();
    expect(screen.getByText(/1 changed/)).toBeTruthy();
    expect(within(screen.getByRole('table')).getByText('SIM-P001')).toBeTruthy();
    expect(within(screen.getByRole('table')).getByText('SIM-P002')).toBeTruthy();
  });

  it('disables "Run simulation" and shows the warning badge when not on the sim database', () => {
    hooks.useSimulationOverview.mockReturnValue(overview({ sim_db_active: false }));
    hooks.useScenarios.mockReturnValue(scenariosQuery([row()]));
    render(<SimulationView />);

    expect(screen.getByText(/not on sim db - run disabled/i)).toBeTruthy();
    expect(screen.getByRole('button', { name: /run simulation/i })).toBeDisabled();
  });

  it('opens the run confirmation dialog on click', () => {
    hooks.useSimulationOverview.mockReturnValue(overview());
    hooks.useScenarios.mockReturnValue(scenariosQuery([row()]));
    render(<SimulationView />);

    fireEvent.click(screen.getByRole('button', { name: /run simulation/i }));
    expect(screen.getByText(/run the simulation\?/i)).toBeTruthy();
  });

  it('opens the destructive bless confirmation dialog on click', () => {
    hooks.useSimulationOverview.mockReturnValue(overview());
    hooks.useScenarios.mockReturnValue(scenariosQuery([row()]));
    render(<SimulationView />);

    fireEvent.click(screen.getByRole('button', { name: /bless baseline/i }));
    expect(screen.getByText(/bless this run as the baseline\?/i)).toBeTruthy();
  });

  it('opens the diff sheet when a row is clicked', async () => {
    hooks.useSimulationOverview.mockReturnValue(overview());
    hooks.useScenarios.mockReturnValue(scenariosQuery([row()]));
    hooks.useScenarioDiff.mockReturnValue({
      data: { code: 'SIM-P001', status: 'SAME', diffs: [], current: { title: 'Steady high demand, low stock' }, baseline: null },
      isLoading: false,
      isError: false,
      error: null,
    });
    render(<SimulationView />);

    fireEvent.click(within(screen.getByRole('table')).getByText('SIM-P001'));
    await waitFor(() => expect(screen.getByText(/field-level diff vs the blessed baseline/i)).toBeTruthy());
  });
});

/** Radix TabsTrigger activates on mousedown; click alone is not enough in jsdom. */
function selectTab(name: RegExp) {
  const tab = screen.getByRole('tab', { name });
  fireEvent.mouseDown(tab, { button: 0 });
  fireEvent.click(tab);
}

describe('SimulationView - Baseline diff / Planning view tabs', () => {
  it('opens on the Baseline diff tab, showing the scenario grid and not the planning tab', () => {
    hooks.useSimulationOverview.mockReturnValue(overview());
    hooks.useScenarios.mockReturnValue(scenariosQuery([row()]));
    render(<SimulationView />);

    expect(screen.getByRole('table')).toBeTruthy();
    expect(screen.queryByText(/planning-tab/)).toBeNull();
  });

  it('switches to the Planning view tab and passes simDbActive through', () => {
    hooks.useSimulationOverview.mockReturnValue(overview({ sim_db_active: true }));
    hooks.useScenarios.mockReturnValue(scenariosQuery([row()]));
    render(<SimulationView />);

    selectTab(/planning view/i);

    expect(screen.getByText(/planning-tab simDbActive=true/)).toBeTruthy();
  });

  it('passes simDbActive=false through when this backend is not on the sim database', () => {
    hooks.useSimulationOverview.mockReturnValue(overview({ sim_db_active: false }));
    hooks.useScenarios.mockReturnValue(scenariosQuery([row()]));
    render(<SimulationView />);

    selectTab(/planning view/i);

    expect(screen.getByText(/planning-tab simDbActive=false/)).toBeTruthy();
  });
});
