import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import { getAccessAgents, getAccessAgent, createAccessAgent, updateAccessAgent, deleteAccessAgent, getContactAccessAgents, createContactAgentAccess, updateContactAgentAccess, deleteContactAgentAccess, getRespondSyncedUsers } from '../services/accessAgentService';
import type { AccessAgentFormData, ContactAgentAccessFormData } from '../types/accessAgent.types';

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
    retry: 1,
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
    onError: (error: Error) => toast.error(error.message || 'Failed to create access agent'),
  });
}

export function useUpdateAccessAgent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<AccessAgentFormData> }) => updateAccessAgent(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['access-agents'] });
      queryClient.invalidateQueries({ queryKey: ['access-agent'] });
      toast.success('Access agent updated successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to update access agent'),
  });
}

export function useDeleteAccessAgent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteAccessAgent(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['access-agents'] });
      toast.success('Access agent deleted successfully');
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

export function useRespondSyncedUsers(query?: string) {
  return useQuery({
    queryKey: ['respond-synced-users', query],
    queryFn: () => getRespondSyncedUsers(query),
    staleTime: 1000 * 60 * 5,
    retry: 1,
  });
}
