import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api';

export interface ComplaintStatusSelectOption {
  id: string;
  status_code: string;
  status_name: string;
  description?: string | null;
  sequence: number;
}

export function useComplaintStatusSelectQuery() {
  return useQuery({
    queryKey: ['complaint-statuses-select'],
    queryFn: async () => {
      const response = await apiFetch(
        '/api/v1/complaint-management/complaint-statuses',
      );
      if (!response.ok) throw new Error('Failed to fetch complaint statuses');
      const data = await response.json();
      return data.data as ComplaintStatusSelectOption[];
    },
    staleTime: 1000 * 60 * 5, // 5 minutes
    gcTime: 1000 * 60 * 30, // 30 minutes
  });
}
