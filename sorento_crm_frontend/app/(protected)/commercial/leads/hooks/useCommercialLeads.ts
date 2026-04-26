import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import {
  addLeadNote,
  convertCommercialLead,
  createCommercialLead,
  deleteCommercialLead,
  getCommercialLead,
  getCommercialLeads,
  getLeadNotes,
  getLeadRelated,
  updateCommercialLead,
} from '../services/leadService';
import type { CommercialLeadConvertPayload, CommercialLeadCreatePayload, CommercialLeadUpdatePayload } from '../types/lead.types';

export function useCommercialLeads(
  params: DataGridApiFetchParams & {
    customer_id?: string;
    owner_user_id?: string;
    lead_stage_id?: string;
    open_pipeline_only?: boolean;
    customer_active_only?: boolean;
    created_from?: string;
    created_to?: string;
  },
  options?: { enabled?: boolean },
) {
  return useQuery({
    queryKey: [
      'commercial-leads',
      params.pageIndex,
      params.pageSize,
      params.sorting,
      params.searchQuery,
      params.customer_id,
      params.owner_user_id,
      params.lead_stage_id,
      params.open_pipeline_only,
      params.customer_active_only,
      params.created_from,
      params.created_to,
    ],
    queryFn: () => getCommercialLeads(params),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
    retry: 1,
    enabled: options?.enabled ?? true,
  });
}

export function useLeadRelated(leadId: string | null) {
  return useQuery({
    queryKey: ['commercial-lead-related', leadId],
    queryFn: () => {
      if (!leadId) throw new Error('Lead id required');
      return getLeadRelated(leadId);
    },
    enabled: !!leadId,
    staleTime: 20_000,
    retry: 1,
  });
}

export function useCommercialLead(id: string | null) {
  return useQuery({
    queryKey: ['commercial-lead', id],
    queryFn: () => {
      if (!id) throw new Error('Lead id required');
      return getCommercialLead(id);
    },
    enabled: !!id,
    retry: 1,
  });
}

export function useLeadNotes(leadId: string | null) {
  return useQuery({
    queryKey: ['commercial-lead-notes', leadId],
    queryFn: () => {
      if (!leadId) throw new Error('Lead id required');
      return getLeadNotes(leadId);
    },
    enabled: !!leadId,
    retry: 1,
  });
}

export function useCreateCommercialLead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CommercialLeadCreatePayload) => createCommercialLead(data),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['commercial-leads'] });
      toast.success('Lead created');
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to create lead'),
  });
}

export function useUpdateCommercialLead(leadId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CommercialLeadUpdatePayload) => updateCommercialLead(leadId, data),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['commercial-leads'] });
      void qc.invalidateQueries({ queryKey: ['commercial-lead', leadId] });
      void qc.invalidateQueries({ queryKey: ['commercial-lead-related', leadId] });
      void qc.invalidateQueries({ queryKey: ['commercial-lead-respond-contacts', leadId] });
      toast.success('Lead updated');
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to update lead'),
  });
}

export function useDeleteCommercialLead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteCommercialLead(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['commercial-leads'] });
      toast.success('Lead deleted');
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to delete lead'),
  });
}

export function useAddLeadNote(leadId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: string) => addLeadNote(leadId, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['commercial-lead-notes', leadId] });
      toast.success('Note added');
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to add note'),
  });
}

export function useConvertCommercialLead(leadId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CommercialLeadConvertPayload) => convertCommercialLead(leadId, data),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['commercial-leads'] });
      void qc.invalidateQueries({ queryKey: ['commercial-lead', leadId] });
      void qc.invalidateQueries({ queryKey: ['commercial-lead-related', leadId] });
      toast.success('Lead converted');
    },
    onError: (e: Error) => toast.error(e.message || 'Conversion failed'),
  });
}
