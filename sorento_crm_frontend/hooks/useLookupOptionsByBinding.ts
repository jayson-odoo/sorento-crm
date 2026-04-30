import { useQuery } from '@tanstack/react-query';
import { getLookupOptionsByBinding } from '@/lib/lookupBindingService';

export function useLookupOptionsByBinding(table: string, column: string) {
  return useQuery({
    queryKey: ['lookup-by-binding', table, column],
    queryFn: () => getLookupOptionsByBinding(table, column),
    staleTime: 60_000,
  });
}
