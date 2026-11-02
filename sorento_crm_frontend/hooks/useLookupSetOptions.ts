import { useQuery } from '@tanstack/react-query';
import { getLookupSetOptions } from '@/lib/lookupBindingService';

/** Options of one lookup set by key; cached a minute like the by-binding read. */
export function useLookupSetOptions(setKey: string, options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: ['lookup-set-options', setKey],
    queryFn: () => getLookupSetOptions(setKey),
    staleTime: 60_000,
    enabled: (options.enabled ?? true) && Boolean(setKey),
  });
}
