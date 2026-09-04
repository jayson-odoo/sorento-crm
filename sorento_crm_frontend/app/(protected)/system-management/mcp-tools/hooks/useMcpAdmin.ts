import { useQuery } from '@tanstack/react-query';
import { listMcpToolsCatalog } from '../services/mcpAdminService';

/**
 * The whole catalogue in one read (limit 500), with an Active-only toggle. It
 * does NOT keep the previous answer: there are no pages here, so the only key
 * change is the toggle itself, and keeping the last answer through it means the
 * reader flips to Active and still sees the inactive rows. That is the toggle
 * failing to work, which is worse than the flicker keepPreviousData avoids.
 * Allowlisted in `lib/list-query/options.inventory.test.ts` for that reason.
 */
export function useMcpToolsCatalog(params: { is_active?: boolean } = {}) {
  return useQuery({
    queryKey: ['mcp-tools-catalog', params.is_active ?? true],
    queryFn: () => listMcpToolsCatalog({ is_active: params.is_active ?? true, limit: 500 }),
    staleTime: 1000 * 60,
  });
}
