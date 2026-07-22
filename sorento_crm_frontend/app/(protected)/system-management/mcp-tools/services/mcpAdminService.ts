import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

export interface McpToolCatalogRow {
  id: string;
  tool_name: string;
  description: string | null;
  module_key: string;
}

export async function listMcpToolsCatalog(params: {
  is_active?: boolean;
  limit?: number;
} = {}): Promise<McpToolCatalogRow[]> {
  const usp = new URLSearchParams();
  usp.set('is_active', String(params.is_active ?? true));
  usp.set('limit', String(params.limit ?? 500));
  const response = await apiFetch(`/api/system/mcp-tools?${usp.toString()}`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to fetch MCP tools'));
  }
  return response.json();
}
