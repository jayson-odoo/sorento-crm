import { useQuery } from '@tanstack/react-query';
import { getHealthSummary } from '../services/healthService';

export function useHealthSummary(range?: { date_from?: string; date_to?: string }) {
  return useQuery({
    queryKey: ['system-health-summary', range?.date_from ?? null, range?.date_to ?? null],
    queryFn: () => getHealthSummary(range),
    staleTime: 1000 * 30,
    retry: 1,
  });
}
