import { useQuery } from '@tanstack/react-query';
import { getHealthSummary } from '../services/healthService';

export function useHealthSummary() {
  return useQuery({
    queryKey: ['system-health-summary'],
    queryFn: getHealthSummary,
    staleTime: 1000 * 30,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}
