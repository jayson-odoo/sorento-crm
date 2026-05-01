import { useQuery } from '@tanstack/react-query';
import { listMcpAccessLog, listMcpToolsCatalog } from '../services/mcpAdminService';

export function useMcpToolsCatalog(params: { is_active?: boolean } = {}) {
  return useQuery({
    queryKey: ['mcp-tools-catalog', params.is_active ?? true],
    queryFn: () => listMcpToolsCatalog({ is_active: params.is_active ?? true, limit: 500 }),
    staleTime: 1000 * 60,
  });
}

export function useMcpAccessLog(params: { decision?: string; tool_name?: string } = {}) {
  return useQuery({
    queryKey: ['mcp-access-log', params.decision ?? null, params.tool_name ?? null],
    queryFn: () => listMcpAccessLog({ ...params, limit: 200 }),
    staleTime: 1000 * 30,
  });
}
