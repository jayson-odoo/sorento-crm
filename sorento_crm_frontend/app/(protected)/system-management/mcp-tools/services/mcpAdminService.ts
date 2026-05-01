import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

export interface McpToolCatalogRow {
  id: string;
  tool_name: string;
  description: string | null;
  module_key: string;
  current_agent_id: string | null;
  current_agent_name: string | null;
}

export interface McpAccessLogRow {
  id: string;
  tool_name: string;
  contact_external_id: string | null;
  respond_contact_id: string | null;
  respond_workspace_id: string | null;
  decision: string;
  matched_agent_id: string | null;
  ts: string;
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

export async function listMcpAccessLog(params: {
  decision?: string;
  tool_name?: string;
  limit?: number;
} = {}): Promise<McpAccessLogRow[]> {
  const usp = new URLSearchParams();
  if (params.decision) usp.set('decision', params.decision);
  if (params.tool_name) usp.set('tool_name', params.tool_name);
  usp.set('limit', String(params.limit ?? 200));
  const response = await apiFetch(`/api/system/mcp-access/log?${usp.toString()}`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to fetch MCP access log'));
  }
  return response.json();
}
