'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import {
  blessBaseline,
  getOverview,
  getScenarioDiff,
  getScenarios,
  runSimulation,
} from '../services/simulationService';

const OVERVIEW_KEY = ['scm', 'simulation', 'overview'] as const;
const SCENARIOS_KEY = ['scm', 'simulation', 'scenarios'] as const;
const DIFF_KEY = (code: string) => ['scm', 'simulation', 'diff', code] as const;

export function useSimulationOverview() {
  return useQuery({
    queryKey: OVERVIEW_KEY,
    queryFn: getOverview,
    retry: 1,
  });
}

export function useScenarios() {
  return useQuery({
    queryKey: SCENARIOS_KEY,
    queryFn: getScenarios,
    retry: 1,
  });
}

/** One scenario's full diff. Only fetched once the user opens its detail sheet. */
export function useScenarioDiff(code: string | null) {
  return useQuery({
    queryKey: DIFF_KEY(code ?? ''),
    queryFn: () => getScenarioDiff(code as string),
    enabled: code !== null,
    retry: 1,
  });
}

/**
 * Wipe + reseed the sim database, run the engine once, write the new snapshot.
 * Refreshes both the overview strip and the scenario grid on success - a run
 * changes both the "last run" timestamp and every row's `current` figures.
 */
export function useRunSimulation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (blessAsBaseline: boolean) => runSimulation(blessAsBaseline),
    onSuccess: (result) => {
      void qc.invalidateQueries({ queryKey: OVERVIEW_KEY });
      void qc.invalidateQueries({ queryKey: SCENARIOS_KEY });
      void qc.invalidateQueries({ queryKey: ['scm', 'simulation', 'diff'] });
      toast.success(
        result.blessed
          ? `Simulation run complete and blessed as the new baseline (${result.recommendation_count} recommendations).`
          : `Simulation run complete (${result.recommendation_count} recommendations).`,
      );
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

/** Copies the last run over the blessed baseline. Separate from the run itself so a
 *  run can be inspected before it becomes the reference every future run is diffed
 *  against. */
export function useBlessBaseline() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: blessBaseline,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: OVERVIEW_KEY });
      void qc.invalidateQueries({ queryKey: SCENARIOS_KEY });
      void qc.invalidateQueries({ queryKey: ['scm', 'simulation', 'diff'] });
      toast.success('Baseline blessed');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}
