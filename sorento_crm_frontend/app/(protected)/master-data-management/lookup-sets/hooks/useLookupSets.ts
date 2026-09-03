import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import {
  listLookupSets, getLookupSet, createLookupSet, updateLookupSet,
  listOptions, createOption, updateOption, deleteOption,
  listBindings, addBinding, removeBinding, setBindingDefaultValue,
  listEligibility, resolveLookup,
} from '../services/lookupSetService';
import type { LookupSetFormData, LookupOptionFormData } from '../types/lookup.types';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';

const KEY = 'lookup-sets';

export function useLookupSets(params: DataGridApiFetchParams) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: [KEY, params.pageIndex, params.pageSize, params.sorting, params.searchQuery],
    queryFn: () => listLookupSets(params),
    staleTime: 30_000,
  });
}

export function useLookupSet(id: string | null) {
  return useQuery({
    queryKey: [KEY, id],
    queryFn: () => getLookupSet(id!),
    enabled: !!id,
  });
}

export function useCreateLookupSet() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: LookupSetFormData) => createLookupSet(data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: [KEY] }); toast.success('Lookup set created'); },
    onError: (e: Error) => toast.error(e.message),
  });
}
export function useUpdateLookupSet() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<LookupSetFormData> }) => updateLookupSet(id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: [KEY] }); toast.success('Updated'); },
    onError: (e: Error) => toast.error(e.message),
  });
}
// Options
export function useOptions(setId: string | null) {
  return useQuery({
    queryKey: [KEY, setId, 'options'],
    queryFn: () => listOptions(setId!),
    enabled: !!setId,
  });
}
export function useCreateOption(setId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: LookupOptionFormData) => createOption(setId, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: [KEY, setId, 'options'] }); toast.success('Option added'); },
    onError: (e: Error) => toast.error(e.message),
  });
}
export function useUpdateOption(setId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<LookupOptionFormData> }) => updateOption(setId, id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: [KEY, setId, 'options'] }); toast.success('Option updated'); },
    onError: (e: Error) => toast.error(e.message),
  });
}
export function useDeleteOption(setId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteOption(setId, id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: [KEY, setId, 'options'] }); toast.success('Option deleted'); },
    onError: (e: Error) => toast.error(e.message),
  });
}

// Bindings
export function useBindings(setId: string | null) {
  return useQuery({
    queryKey: [KEY, setId, 'bindings'],
    queryFn: () => listBindings(setId!),
    enabled: !!setId,
  });
}
export function useAddBinding(setId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ table_name, column_name }: { table_name: string; column_name: string }) =>
      addBinding(setId, table_name, column_name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [KEY, setId, 'bindings'] });
      qc.invalidateQueries({ queryKey: ['lookup-eligibility'] });
      toast.success('Binding added');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}
export function useRemoveBinding(setId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (bindingId: string) => removeBinding(setId, bindingId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [KEY, setId, 'bindings'] });
      qc.invalidateQueries({ queryKey: ['lookup-eligibility'] });
      toast.success('Binding removed');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}
export function useSetBindingDefaultValue(setId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ bindingId, default_value }: { bindingId: string; default_value: string | null }) =>
      setBindingDefaultValue(setId, bindingId, default_value),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [KEY, setId, 'bindings'] });
      toast.success('Default updated');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

// Eligibility
export function useEligibility(available = false) {
  return useQuery({
    queryKey: ['lookup-eligibility', available],
    queryFn: () => listEligibility(available),
  });
}

// Resolve
export function useResolve() {
  return useMutation({
    mutationFn: ({ set_key, raw, locale }: { set_key: string; raw: string; locale?: string }) =>
      resolveLookup(set_key, raw, locale),
  });
}
