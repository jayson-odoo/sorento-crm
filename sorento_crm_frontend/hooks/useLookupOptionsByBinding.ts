import { useQuery } from '@tanstack/react-query';
import { getLookupOptionsByBinding } from '@/lib/lookupBindingService';

/**
 * `enabled` is for a caller that mounts the hook unconditionally (rules of
 * hooks) but only needs the options for one of the shapes it renders - e.g. the
 * shared Revisions tab, which serves stock inquiries as well as the two request
 * types and must not fetch a purchase-request binding for an inquiry.
 */
export function useLookupOptionsByBinding(
  table: string,
  column: string,
  options?: { enabled?: boolean },
) {
  return useQuery({
    queryKey: ['lookup-by-binding', table, column],
    queryFn: () => getLookupOptionsByBinding(table, column),
    staleTime: 60_000,
    enabled: options?.enabled !== false,
  });
}
