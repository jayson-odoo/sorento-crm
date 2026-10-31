import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

/**
 * The MCP server's bearer token (lane MCP-TOKEN-UI,
 * documentation/plans/security/PLAN-mcp-token-ui-30oct.md). All four calls need
 * `user_management.settings.secrets` (admin only).
 *
 * READ    GET  /api/v1/user-management/settings/mcp-token            -> McpTokenState
 * ROTATE  POST /api/v1/user-management/settings/mcp-token/rotate     -> McpTokenState & { token }
 *   Generates the first token, or a new one; the old one stays valid for `grace_hours`.
 *   `token` is in this answer only: it is never readable again.
 * ENFORCE PUT  /api/v1/user-management/settings/mcp-token  { enforce } -> McpTokenState
 *   409 when switching on with no token.
 * REVOKE  POST /api/v1/user-management/settings/mcp-token/revoke-previous -> McpTokenState
 */

export interface McpTokenState {
  configured: boolean;
  /** "****" + the last 4 characters, null when unset or unreadable. */
  masked: string | null;
  /** The saved token cannot be decrypted (the encryption key changed). */
  unreadable: boolean;
  enforce: boolean;
  rotated_at: string | null;
  /** ISO time the previous token stops working, null when there is none. */
  previous_valid_until: string | null;
  grace_hours: number;
}

export interface McpTokenRotated extends McpTokenState {
  token: string;
}

const ENDPOINT = '/api/user-management/settings/mcp-token';

async function call<T>(
  path: string,
  init: RequestInit,
  fallback: string,
): Promise<T> {
  const response = await apiFetch(path, init);
  if (!response.ok) {
    throw new Error(await extractApiError(response, fallback));
  }
  return (await response.json()) as T;
}

export function getMcpToken(): Promise<McpTokenState> {
  return call(ENDPOINT, {}, 'Failed to load the MCP token');
}

export function rotateMcpToken(): Promise<McpTokenRotated> {
  return call(
    `${ENDPOINT}/rotate`,
    { method: 'POST' },
    'Failed to generate the MCP token',
  );
}

export function setMcpEnforce(enforce: boolean): Promise<McpTokenState> {
  return call(
    ENDPOINT,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enforce }),
    },
    'Failed to change Enforce',
  );
}

export function revokePreviousMcpToken(): Promise<McpTokenState> {
  return call(
    `${ENDPOINT}/revoke-previous`,
    { method: 'POST' },
    'Failed to revoke the previous token',
  );
}
