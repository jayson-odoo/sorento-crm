import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const svc = vi.hoisted(() => ({
  getOverview: vi.fn(),
  getScenarios: vi.fn(),
  getScenarioDiff: vi.fn(),
  runSimulation: vi.fn(),
  blessBaseline: vi.fn(),
}));
vi.mock('../services/simulationService', () => svc);

const toastSuccess = vi.fn();
const toastError = vi.fn();
vi.mock('@/lib/toast', () => ({
  toast: { success: (...a: unknown[]) => toastSuccess(...a), error: (...a: unknown[]) => toastError(...a) },
}));

import {
  useBlessBaseline,
  useRunSimulation,
  useScenarioDiff,
  useScenarios,
  useSimulationOverview,
} from './useSimulation';

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return React.createElement(QueryClientProvider, { client }, children);
}

beforeEach(() => {
  svc.getOverview.mockReset();
  svc.getScenarios.mockReset();
  svc.getScenarioDiff.mockReset();
  svc.runSimulation.mockReset();
  svc.blessBaseline.mockReset();
  toastSuccess.mockReset();
  toastError.mockReset();
});

describe('useSimulationOverview', () => {
  it('loads the overview', async () => {
    svc.getOverview.mockResolvedValue({
      sim_db_active: true,
      baseline_exists: true,
      baseline_blessed_at: null,
      current_exists: true,
      current_run_at: null,
      latest_run_id: null,
      scenario_count: 38,
    });
    const { result } = renderHook(() => useSimulationOverview(), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.scenario_count).toBe(38);
  });
});

describe('useScenarios', () => {
  it('loads the scenario rows', async () => {
    svc.getScenarios.mockResolvedValue([{ code: 'SIM-P001', status: 'SAME' }]);
    const { result } = renderHook(() => useScenarios(), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(1);
  });
});

describe('useScenarioDiff', () => {
  it('is disabled when code is null', () => {
    const { result } = renderHook(() => useScenarioDiff(null), { wrapper });
    expect(result.current.fetchStatus).toBe('idle');
    expect(svc.getScenarioDiff).not.toHaveBeenCalled();
  });

  it('fetches once a code is provided', async () => {
    svc.getScenarioDiff.mockResolvedValue({ code: 'SIM-P001', status: 'SAME', diffs: [] });
    const { result } = renderHook(() => useScenarioDiff('SIM-P001'), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(svc.getScenarioDiff).toHaveBeenCalledWith('SIM-P001');
  });
});

describe('useRunSimulation', () => {
  it('toasts success naming the recommendation count on a plain run', async () => {
    svc.runSimulation.mockResolvedValue({
      run_id: 'run-1',
      blessed: false,
      buy_count: 1,
      disposition_count: 0,
      exception_count: 0,
      total_cash_impact: 100,
      recommendation_count: 3,
    });
    const { result } = renderHook(() => useRunSimulation(), { wrapper });
    await act(async () => {
      await result.current.mutateAsync(false);
    });
    expect(svc.runSimulation).toHaveBeenCalledWith(false);
    expect(toastSuccess).toHaveBeenCalledWith(expect.stringContaining('3 recommendations'));
  });

  it('toasts an error message on failure', async () => {
    svc.runSimulation.mockRejectedValue(new Error('not on sim db'));
    const { result } = renderHook(() => useRunSimulation(), { wrapper });
    await act(async () => {
      await result.current.mutateAsync(false).catch(() => {});
    });
    expect(toastError).toHaveBeenCalledWith('not on sim db');
  });
});

describe('useBlessBaseline', () => {
  it('toasts success on bless', async () => {
    svc.blessBaseline.mockResolvedValue({ blessed: true, baseline_blessed_at: '2026-08-01T00:00:00' });
    const { result } = renderHook(() => useBlessBaseline(), { wrapper });
    await act(async () => {
      await result.current.mutateAsync();
    });
    expect(toastSuccess).toHaveBeenCalledWith('Baseline blessed');
  });
});
