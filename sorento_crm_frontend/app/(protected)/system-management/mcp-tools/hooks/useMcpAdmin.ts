import { useQuery } from '@tanstack/react-query';
import { listMcpToolsCatalog } from '../services/mcpAdminService';

export function useMcpToolsCatalog(params: { is_active?: boolean } = {}) {
  return useQuery({
    queryKey: ['mcp-tools-catalog', params.is_active ?? true],
    queryFn: () => listMcpToolsCatalog({ is_active: params.is_active ?? true, limit: 500 }),
    staleTime: 1000 * 60,
  });
}
