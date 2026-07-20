/** One external/MCP request, as recorded by ApiCallLogMiddleware. */
export interface ApiCallLogRow {
  id: string;
  endpoint: string;
  method: string;
  /** 'mcp' | 'n8n' | 'unknown' | any new caller that sends X-Source. */
  source: string;
  /** MCP tool name (X-Tool-Name) when source is 'mcp'. */
  tool_name: string | null;
  actor: string | null;
  status_code: number | null;
  outcome: 'success' | 'client_error' | 'server_error';
  latency_ms: number | null;
  /** Joins this server-side span to the MCP client's own elapsed_ms. */
  correlation_id: string | null;
  /** Redacted + truncated. NULLed by the prune task at 30d. */
  request_payload: string | null;
  response_payload: string | null;
  error_message: string | null;
  created_at: string;
}

export interface ApiCallLogListResponse {
  data: ApiCallLogRow[];
  total: number;
  page: number;
  limit: number;
}

export interface ApiCallLogFilters {
  date_from?: string;
  date_to?: string;
  source?: string;
  outcome?: string;
  endpoint?: string;
  correlation_id?: string;
  min_latency_ms?: number;
  search?: string;
  page?: number;
  limit?: number;
  sort?: string;
  dir?: 'asc' | 'desc';
}
