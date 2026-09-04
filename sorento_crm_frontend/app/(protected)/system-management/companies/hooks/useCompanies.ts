import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import {
  addCompanyContact,
  addCompanyUser,
  createCompany,
  deleteCompany,
  getAvailableContacts,
  getCompanies,
  getCompany,
  getCompanyContacts,
  getCompanyUsers,
  removeCompanyContact,
  removeCompanyUser,
  updateCompany,
} from '../services/companyService';
import type { CompanyFormData, CompanyUser } from '../types/company.types';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';

export function useCompanies(params: DataGridApiFetchParams) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: ['companies', params.pageIndex, params.pageSize, params.sorting, params.searchQuery],
    queryFn: () => getCompanies(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    retry: 1,
  });
}

export function useCompany(id: string | null) {
  return useQuery({
    queryKey: ['company', id],
    queryFn: () => {
      if (!id) throw new Error('Company ID is required');
      return getCompany(id);
    },
    enabled: !!id,
    retry: 1,
  });
}

export function useCreateCompany() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CompanyFormData) => createCompany(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['companies'] });
      toast.success('Company created successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to create company'),
  });
}

export function useUpdateCompany() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: CompanyFormData }) => updateCompany(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['companies'] });
      queryClient.invalidateQueries({ queryKey: ['company'] });
      toast.success('Company updated successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to update company'),
  });
}

export function useDeleteCompany() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteCompany(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['companies'] });
      toast.success('Company deleted successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to delete company'),
  });
}

// ── Access management ─────────────────────────────────────────────────────────

export function useCompanyUsers(companyId: string | null) {
  return useQuery({
    queryKey: ['company-users', companyId],
    queryFn: () => {
      if (!companyId) throw new Error('Company ID is required');
      return getCompanyUsers(companyId);
    },
    enabled: !!companyId,
  });
}

export function useAddCompanyUser(companyId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (user: CompanyUser) => addCompanyUser(companyId, user),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['company-users', companyId] });
      queryClient.invalidateQueries({ queryKey: ['companies'] });
      toast.success('User assigned');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to assign user'),
  });
}

export function useRemoveCompanyUser(companyId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (userId: string) => removeCompanyUser(companyId, userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['company-users', companyId] });
      queryClient.invalidateQueries({ queryKey: ['companies'] });
      toast.success('User removed');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to remove user'),
  });
}

export function useCompanyContacts(companyId: string | null) {
  return useQuery({
    queryKey: ['company-contacts', companyId],
    queryFn: () => {
      if (!companyId) throw new Error('Company ID is required');
      return getCompanyContacts(companyId);
    },
    enabled: !!companyId,
  });
}

export function useAvailableContacts(companyId: string | null) {
  return useQuery({
    queryKey: ['company-contacts-available', companyId],
    queryFn: () => {
      if (!companyId) throw new Error('Company ID is required');
      return getAvailableContacts(companyId);
    },
    enabled: !!companyId,
  });
}

export function useAddCompanyContact(companyId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (contactId: string) => addCompanyContact(companyId, contactId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['company-contacts', companyId] });
      queryClient.invalidateQueries({ queryKey: ['company-contacts-available', companyId] });
      queryClient.invalidateQueries({ queryKey: ['companies'] });
      toast.success('Contact tagged');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to tag contact'),
  });
}

export function useRemoveCompanyContact(companyId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (contactId: string) => removeCompanyContact(companyId, contactId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['company-contacts', companyId] });
      queryClient.invalidateQueries({ queryKey: ['company-contacts-available', companyId] });
      queryClient.invalidateQueries({ queryKey: ['companies'] });
      toast.success('Contact removed');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to remove contact'),
  });
}
