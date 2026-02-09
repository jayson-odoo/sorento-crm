import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import {
  getComplaints,
  getComplaint,
  createComplaint,
  updateComplaint,
  deleteComplaint,
  linkComplaintAttachment,
  deleteComplaintAttachment,
} from '../services/complaintService';
import type { ComplaintFormData } from '../types/complaint.types';

export function useComplaints(params: DataGridApiFetchParams) {
  return useQuery({
    queryKey: [
      'complaints',
      params.pageIndex,
      params.pageSize,
      params.sorting,
      params.searchQuery,
    ],
    queryFn: () => getComplaints(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useComplaint(id: string | null) {
  return useQuery({
    queryKey: ['complaint', id],
    queryFn: () => {
      if (!id) throw new Error('Complaint ID is required');
      return getComplaint(id);
    },
    enabled: !!id,
    retry: 1,
  });
}

export function useCreateComplaint() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: ComplaintFormData) => createComplaint(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['complaints'] });
      toast.success('Complaint created successfully');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to create complaint'),
  });
}

export function useUpdateComplaint() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      data,
    }: {
      id: string;
      data: Partial<ComplaintFormData>;
    }) => updateComplaint(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['complaints'] });
      queryClient.invalidateQueries({ queryKey: ['complaint'] });
      toast.success('Complaint updated successfully');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to update complaint'),
  });
}

export function useDeleteComplaint() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteComplaint(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['complaints'] });
      toast.success('Complaint deleted successfully');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to delete complaint'),
  });
}

export function useLinkComplaintAttachment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      complaintId,
      attachmentId,
    }: {
      complaintId: string;
      attachmentId: string;
    }) => linkComplaintAttachment(complaintId, attachmentId),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['complaint', variables.complaintId] });
      queryClient.invalidateQueries({ queryKey: ['complaints'] });
      toast.success('Attachment linked successfully');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to link attachment'),
  });
}

export function useDeleteComplaintAttachment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (linkId: string) => deleteComplaintAttachment(linkId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['complaint'] });
      queryClient.invalidateQueries({ queryKey: ['complaints'] });
      toast.success('Attachment unlinked successfully');
    },
    onError: (error: Error) =>
      toast.error(error.message || 'Failed to unlink attachment'),
  });
}
