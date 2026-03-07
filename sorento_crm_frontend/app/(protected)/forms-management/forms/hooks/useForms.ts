import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import { getForms, getForm, createForm, updateForm, deleteForm, bulkDeleteForms, duplicateForm, publishForm, getFormVersions } from '../services/formService';
import type { FormFormData } from '../types/form.types';

export function useForms(params: DataGridApiFetchParams & { language?: string; status?: string; purpose?: string }) {
  return useQuery({
    queryKey: ['forms', params.pageIndex, params.pageSize, params.sorting, params.searchQuery, params.language, params.status, params.purpose],
    queryFn: () => getForms(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

export function useForm(id: string | null) {
  return useQuery({
    queryKey: ['form', id],
    queryFn: () => {
      if (!id) throw new Error('Form ID is required');
      return getForm(id);
    },
    enabled: !!id,
    retry: 1,
  });
}

export function useFormVersions(formId: string | null) {
  return useQuery({
    queryKey: ['form-versions', formId],
    queryFn: () => {
      if (!formId) throw new Error('Form ID is required');
      return getFormVersions(formId);
    },
    enabled: !!formId,
    retry: 1,
  });
}

export function useCreateForm() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: FormFormData) => createForm(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['forms'] });
      toast.success('Form created successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to create form'),
  });
}

export function useUpdateForm() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<FormFormData> }) => updateForm(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['forms'] });
      queryClient.invalidateQueries({ queryKey: ['form'] });
      toast.success('Form updated successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to update form'),
  });
}

export function useDeleteForm() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteForm(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['forms'] });
      toast.success('Form deleted successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to delete form'),
  });
}

export function useBulkDeleteForms() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (ids: string[]) => bulkDeleteForms(ids),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['forms'] });
      toast.success(result?.message ?? `${result?.deleted_count ?? 0} form(s) deleted`);
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to bulk delete forms'),
  });
}

export function useDuplicateForm() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, newCode }: { id: string; newCode: string }) => duplicateForm(id, newCode),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['forms'] });
      toast.success('Form duplicated successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to duplicate form'),
  });
}

export function usePublishForm() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => publishForm(id),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: ['forms'] });
      queryClient.invalidateQueries({ queryKey: ['form', id] });
      queryClient.invalidateQueries({ queryKey: ['form-versions', id] });
      toast.success('Form published successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to publish form'),
  });
}
