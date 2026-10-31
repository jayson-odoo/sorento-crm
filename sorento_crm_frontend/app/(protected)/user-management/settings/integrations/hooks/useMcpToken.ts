import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';

import {
  getMcpToken,
  revokePreviousMcpToken,
  rotateMcpToken,
  setMcpEnforce,
  type McpTokenRotated,
  type McpTokenState,
} from '../services/mcpTokenService';

export const MCP_TOKEN_KEY = ['mcp-token'];

export function useMcpToken() {
  return useQuery({
    queryKey: MCP_TOKEN_KEY,
    queryFn: getMcpToken,
    retry: 1,
    // The card renders the failure in place with a Retry; no toast on top of it.
    meta: { silent: true },
  });
}

function useStateMutation<V>(
  fn: (v: V) => Promise<McpTokenState>,
  done: string,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: (data) => {
      queryClient.setQueryData(MCP_TOKEN_KEY, data);
      toast.success(done);
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

export function useRotateMcpToken() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => rotateMcpToken(),
    onSuccess: (data: McpTokenRotated) => {
      // The token itself never goes into the query cache: only the card's own state holds it.
      const rest: McpTokenState & { token?: string } = { ...data };
      delete rest.token;
      queryClient.setQueryData(MCP_TOKEN_KEY, rest);
      toast.success('MCP token generated');
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

export function useSetMcpEnforce() {
  return useStateMutation(
    (enforce: boolean) => setMcpEnforce(enforce),
    'Enforce updated',
  );
}

export function useRevokePreviousMcpToken() {
  return useStateMutation(
    () => revokePreviousMcpToken(),
    'Previous token revoked',
  );
}
