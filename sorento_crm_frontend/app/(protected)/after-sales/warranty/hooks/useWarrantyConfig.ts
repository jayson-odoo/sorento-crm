import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import {
  createKind,
  createPolicy,
  createRule,
  createTerm,
  getDefectTypes,
  getKinds,
  getPolicies,
  getPolicy,
  getRules,
  getTerms,
  supersedePolicy,
  testKindRules,
  updateKind,
  updatePolicy,
  updateRule,
  updateTerm,
} from '../services/warrantyConfigService';
import type {
  SupersedeValues,
  WarrantyKindValues,
  WarrantyPolicyValues,
  WarrantyRuleValues,
  WarrantyTermValues,
} from '../types/warranty.types';

type KindsParams = DataGridApiFetchParams & { is_active?: string[]; has_no_rule?: boolean };
type RulesParams = DataGridApiFetchParams & { kind_id?: string[] };

const listOptions = { ...LIST_QUERY_OPTIONS, retry: 1 };

export function usePolicies(params: DataGridApiFetchParams) {
  return useQuery({ ...listOptions, queryKey: ['warranty-policies', params], queryFn: () => getPolicies(params) });
}

export function usePolicy(id: string) {
  return useQuery({ queryKey: ['warranty-policy', id], queryFn: () => getPolicy(id), enabled: !!id, retry: 1 });
}

export function usePolicyTerms(policyId: string) {
  return useQuery({ queryKey: ['warranty-terms', policyId], queryFn: () => getTerms(policyId), enabled: !!policyId, retry: 1 });
}

export function useKinds(params: KindsParams) {
  return useQuery({ ...listOptions, queryKey: ['warranty-kinds', params], queryFn: () => getKinds(params) });
}

/** The pill's N of M: kinds with no rule, and all kinds. */
export function useKindRuleCounts() {
  return useQuery({
    queryKey: ['warranty-kind-rule-counts'],
    queryFn: async () => {
      const base = { pageIndex: 0, pageSize: 1, sorting: [], searchQuery: '' };
      const [without, total] = await Promise.all([getKinds({ ...base, has_no_rule: true }), getKinds(base)]);
      return { without: without.pagination.total, total: total.pagination.total };
    },
    staleTime: 30_000,
  });
}

export function useKindOptions() {
  return useQuery({
    queryKey: ['warranty-kind-options'],
    queryFn: async () =>
      (await getKinds({ pageIndex: 0, pageSize: 200, sorting: [{ id: 'name', desc: false }], searchQuery: '' })).data.map(
        (k) => ({ id: k.id, name: k.name }),
      ),
    staleTime: 60_000,
  });
}

export function useDefectOptions() {
  return useQuery({ queryKey: ['warranty-defect-types'], queryFn: getDefectTypes, staleTime: 60_000 });
}

export function useRules(params: RulesParams) {
  return useQuery({ ...listOptions, queryKey: ['warranty-rules', params], queryFn: () => getRules(params) });
}

function useInvalidate() {
  const queryClient = useQueryClient();
  return () => {
    for (const key of [
      'warranty-policies',
      'warranty-policy',
      'warranty-terms',
      'warranty-kinds',
      'warranty-kind-rule-counts',
      'warranty-kind-options',
      'warranty-rules',
      'service-job',
      'service-jobs',
    ]) {
      void queryClient.invalidateQueries({ queryKey: [key] });
    }
  };
}

function useSaver<V, R>(fn: (v: V) => Promise<R>, ok: string, fail: string) {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      invalidate();
      toast.success(ok);
    },
    onError: (e: Error) => toast.error(e.message || fail),
  });
}

export const useCreatePolicy = () =>
  useSaver((v: WarrantyPolicyValues) => createPolicy(v), 'Policy created', 'Failed to create the policy');
export const useUpdatePolicy = () =>
  useSaver(
    ({ id, values }: { id: string; values: Partial<WarrantyPolicyValues> }) => updatePolicy(id, values),
    'Policy updated',
    'Failed to update the policy',
  );
export const useSupersedePolicy = () =>
  useSaver(
    ({ id, values }: { id: string; values: SupersedeValues }) => supersedePolicy(id, values),
    'Policy superseded',
    'Failed to supersede the policy',
  );
export const useCreateKind = () =>
  useSaver((v: WarrantyKindValues) => createKind(v), 'Kind created', 'Failed to create the kind');
export const useUpdateKind = () =>
  useSaver(
    ({ id, values }: { id: string; values: Partial<WarrantyKindValues> }) => updateKind(id, values),
    'Kind updated',
    'Failed to update the kind',
  );
export const useCreateRule = () =>
  useSaver((v: WarrantyRuleValues) => createRule(v), 'Rule created', 'Failed to create the rule');
export const useUpdateRule = () =>
  useSaver(
    ({ id, values }: { id: string; values: Partial<WarrantyRuleValues> }) => updateRule(id, values),
    'Rule updated',
    'Failed to update the rule',
  );
export function useTestKindRules() {
  return useMutation({
    mutationFn: (productId: string) => testKindRules(productId),
    onError: (e: Error) => toast.error(e.message || 'Failed to test the product'),
  });
}

export const useCreateTerm = () =>
  useSaver((v: Omit<WarrantyTermValues, 'qualifications' | 'exclusions'>) => createTerm(v as WarrantyTermValues), 'Term added', 'Failed to add the term');
export const useUpdateTerm = () =>
  useSaver(
    ({ id, values }: { id: string; values: Partial<Omit<WarrantyTermValues, 'kind_id' | 'policy_id'>> }) =>
      updateTerm(id, values),
    'Term updated',
    'Failed to update the term',
  );
