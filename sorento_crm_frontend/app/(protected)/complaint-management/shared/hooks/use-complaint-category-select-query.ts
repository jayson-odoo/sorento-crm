import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api';

export interface ComplaintCategorySelectOption {
  id: string;
  category_code: string;
  category_name: string;
  description?: string | null;
  severity?: number | null;
}

export function useComplaintCategorySelectQuery() {
  return useQuery({
    queryKey: ['complaint-categories-select'],
    queryFn: async () => {
      const response = await apiFetch(
        '/api/v1/complaints-management/complaint-categories',
      );
      if (!response.ok) throw new Error('Failed to fetch complaint categories');
      const data = await response.json();
      return data.data as ComplaintCategorySelectOption[];
    },
    staleTime: 1000 * 60 * 5, // 5 minutes
    gcTime: 1000 * 60 * 30, // 30 minutes
  });
}
