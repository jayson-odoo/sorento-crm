import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { buildDataGridParams } from '@/lib/api-client';
import {
  useRecordNeighbours,
  type RecordNeighboursResult,
} from '@/hooks/useRecordNeighbours';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import { ACCESS_AGENT_NEIGHBOURS_PATH, getAccessAgents, getAccessAgent, createAccessAgent, updateAccessAgent, deleteAccessAgent, getContactAccessAgents, createContactAgentAccess, updateContactAgentAccess, deleteContactAgentAccess, getAgentTeams, setAgentTeams, getTeams, getAgentMcpTools, getMcpToolsForPicker, setAgentMcpTools, getAgentMcpToolBindings, setAgentMcpToolBindings, type McpToolBindingInput } from '../services/accessAgentService';
import type { AccessAgentFormData, ContactAgentAccessFormData } from '../types/accessAgent.types';

/**
 * Prev/next neighbours of an access agent within the active filtered+sorted list set.
 * Serializes the list query (search) with `buildDataGridParams` — the same
 * serialization the list page uses — so the backend honours filters identically.
 * `page`/`limit` are sent but ignored by the neighbours endpoint.
 */
export function useAccessAgentNeighbours(
  agentId: string | null,
  listParams: DataGridApiFetchParams,
): RecordNeighboursResult {
  const params = buildDataGridParams(listParams);
  return useRecordNeighbours(ACCESS_AGENT_NEIGHBOURS_PATH, agentId, params);
}

export function useAccessAgents(params: DataGridApiFetchParams & { status?: string }) {
  return useQuery({
    queryKey: ['access-agents', params.pageIndex, params.pageSize, params.sorting, params.searchQuery, params.status],
    queryFn: () => getAccessAgents(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useAccessAgent(id: string | null) {
  return useQuery({
    queryKey: ['access-agent', id],
    queryFn: () => {
      if (!id) throw new Error('Access agent ID is required');
      return getAccessAgent(id);
    },
    enabled: !!id,
    // After delete, a refetch would 404 — treat as empty data, not a thrown error (no error toast).
    retry: false,
  });
}

export function useCreateAccessAgent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: AccessAgentFormData) => createAccessAgent(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['access-agents'] });
      toast.success('Access agent created successfully');
    },
  });
}

export function useUpdateAccessAgent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<AccessAgentFormData> }) => updateAccessAgent(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['access-agents'] });
      queryClient.invalidateQueries({ queryKey: ['access-agent'] });
    },
  });
}

export function useDeleteAccessAgent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteAccessAgent(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['access-agents'] });
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to delete access agent'),
  });
}

// Contact Agent Access hooks
export function useContactAccessAgents(agentId: string | null) {
  return useQuery({
    queryKey: ['contact-access-agents', agentId],
    queryFn: () => {
      if (!agentId) throw new Error('Agent ID is required');
      return getContactAccessAgents(agentId);
    },
    enabled: !!agentId,
    retry: 1,
  });
}

export function useCreateContactAgentAccess() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ agentId, data }: { agentId: string; data: ContactAgentAccessFormData }) => createContactAgentAccess(agentId, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['contact-access-agents', variables.agentId] });
      queryClient.invalidateQueries({ queryKey: ['contact-access-agents'] }); // Invalidate all for grouped list and contact-specific queries
      queryClient.invalidateQueries({ queryKey: ['access-agent', variables.agentId] });
      toast.success('Contact access agent created successfully');
    },
    onError: (error: Error) => {
      // Show user-friendly error message
      const errorMessage = error.message || 'Failed to create contact access agent';
      toast.error(errorMessage);
    },
  });
}

export function useUpdateContactAgentAccess() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ agentId, contactId, data }: { agentId: string; contactId: string; data: Partial<ContactAgentAccessFormData> }) => updateContactAgentAccess(agentId, contactId, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['contact-access-agents', variables.agentId] });
      queryClient.invalidateQueries({ queryKey: ['contact-access-agents'] }); // Invalidate all for grouped list
      queryClient.invalidateQueries({ queryKey: ['access-agent', variables.agentId] });
      toast.success('Contact access agent updated successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to update contact access agent'),
  });
}

export function useDeleteContactAgentAccess() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ agentId, contactId }: { agentId: string; contactId: string }) => deleteContactAgentAccess(agentId, contactId),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['contact-access-agents', variables.agentId] });
      queryClient.invalidateQueries({ queryKey: ['contact-access-agents'] }); // Invalidate all for grouped list
      queryClient.invalidateQueries({ queryKey: ['access-agent', variables.agentId] });
      toast.success('Contact access agent deleted successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to delete contact access agent'),
  });
}

export function useAgentTeams(agentId: string | null) {
  return useQuery({
    queryKey: ['agent-teams', agentId],
    queryFn: () => {
      if (!agentId) throw new Error('Agent ID is required');
      return getAgentTeams(agentId);
    },
    enabled: !!agentId,
    retry: 1,
  });
}

export function useSetAgentTeams() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      agentId,
      assignments,
    }: {
      agentId: string;
      assignments: { code: string; team_id: string }[];
    }) => setAgentTeams(agentId, assignments),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['agent-teams', variables.agentId] });
      toast.success('Teams updated');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to set teams'),
  });
}

export function useTeams() {
  return useQuery({
    queryKey: ['teams-list'],
    queryFn: () => getTeams(),
    staleTime: 1000 * 60 * 2,
    retry: 1,
  });
}

export function useAgentMcpTools(agentId: string | null) {
  return useQuery({
    queryKey: ['agent-mcp-tools', agentId],
    queryFn: () => {
      if (!agentId) throw new Error('Agent ID is required');
      return getAgentMcpTools(agentId);
    },
    enabled: !!agentId,
    retry: 1,
  });
}

export function useMcpToolsForPicker() {
  return useQuery({
    queryKey: ['mcp-tools-picker'],
    queryFn: () => getMcpToolsForPicker(),
    staleTime: 1000 * 60 * 2,
    retry: 1,
  });
}

export function useSetAgentMcpTools() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ agentId, toolIds }: { agentId: string; toolIds: string[] }) =>
      setAgentMcpTools(agentId, toolIds),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['agent-mcp-tools', variables.agentId] });
      queryClient.invalidateQueries({ queryKey: ['mcp-tools-picker'] });
      toast.success('MCP tools updated');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to set MCP tools'),
  });
}

export function useAgentMcpToolBindings(agentId: string | null) {
  return useQuery({
    queryKey: ['agent-mcp-tool-bindings', agentId],
    queryFn: () => {
      if (!agentId) throw new Error('Agent ID is required');
      return getAgentMcpToolBindings(agentId);
    },
    enabled: !!agentId,
    retry: 1,
  });
}

export function useSetAgentMcpToolBindings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      agentId,
      bindings,
    }: {
      agentId: string;
      bindings: McpToolBindingInput[];
    }) => setAgentMcpToolBindings(agentId, bindings),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({
        queryKey: ['agent-mcp-tool-bindings', variables.agentId],
      });
      queryClient.invalidateQueries({
        queryKey: ['agent-mcp-tools', variables.agentId],
      });
      queryClient.invalidateQueries({ queryKey: ['mcp-tools-picker'] });
      toast.success('MCP tool bindings updated');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to set MCP tool bindings'),
  });
}
