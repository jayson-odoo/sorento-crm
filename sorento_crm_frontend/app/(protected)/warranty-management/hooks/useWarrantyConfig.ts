'use client';

/**
 * Query + mutation hooks for the warranty configuration area.
 *
 * Every mutation invalidates the counters it can move: a rule change moves
 * `rule_count` on the Kinds tab, a term change moves `term_count` on BOTH the
 * Kinds tab and the Policies list. Invalidating only the list you are looking at
 * is how the zero-flag the slice exists for goes stale.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  createKind,
  createKindRule,
  createPolicy,
  createTerm,
  deleteKind,
  deleteKindRule,
  deletePolicy,
  deleteTerm,
  getPolicy,
  listDefectTypes,
  listKindOptions,
  listKindRules,
  listKinds,
  listPolicies,
  listTermsGroupedByKind,
  supersedePolicy,
  testKindRules,
  updateKind,
  updateKindRule,
  updatePolicy,
  updateTerm,
  type PolicyListQuery,
} from '../services/warrantyConfigService';
import type {
  KindRuleTestRequest,
  WarrantyKindRuleUpdate,
  WarrantyKindRuleWrite,
  WarrantyKindWrite,
  WarrantyPolicyWrite,
  WarrantyTermWrite,
} from '../types/warranty-config.types';

/** One retry, not react-query's default three: a config screen that sits on
 *  skeletons through an exponential backoff reads as hung, not as broken. */
const RETRY = 1;

export const WARRANTY_POLICIES_KEY = ['warranty-policies'];
export const WARRANTY_KINDS_KEY = ['warranty-kinds'];
export const WARRANTY_KIND_RULES_KEY = ['warranty-kind-rules'];
export const WARRANTY_TERMS_KEY = ['warranty-terms'];

function useInvalidator() {
  const qc = useQueryClient();
  return (keys: unknown[][]) => keys.forEach((queryKey) => qc.invalidateQueries({ queryKey }));
}

// ── Policies ────────────────────────────────────────────────────────────────

/** `sorting` is part of the key, not just of the request: react-query serves the
 *  cached page whenever the key is unchanged, so a key without it makes every
 *  column header on the grid a no-op click. The array is safe to key on directly
 *  (the repo's convention everywhere else) - the default key hash is structural,
 *  so a new array with the same contents does not refetch. */
export function usePolicies(params: PolicyListQuery) {
  return useQuery({
    queryKey: [
      ...WARRANTY_POLICIES_KEY,
      params.pageIndex,
      params.pageSize,
      params.searchQuery,
      params.sorting,
    ],
    queryFn: () => listPolicies(params),
    retry: RETRY,
  });
}

export function usePolicy(id: string | null) {
  return useQuery({
    queryKey: [...WARRANTY_POLICIES_KEY, id],
    queryFn: () => getPolicy(id!),
    enabled: !!id,
    retry: RETRY,
  });
}

export function useCreatePolicy() {
  const invalidate = useInvalidator();
  return useMutation({
    mutationFn: (body: WarrantyPolicyWrite) => createPolicy(body),
    onSuccess: () => {
      invalidate([WARRANTY_POLICIES_KEY]);
      toast.success('Policy created');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useUpdatePolicy() {
  const invalidate = useInvalidator();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: WarrantyPolicyWrite }) => updatePolicy(id, body),
    onSuccess: () => {
      invalidate([WARRANTY_POLICIES_KEY]);
      toast.success('Policy updated');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useDeletePolicy() {
  const invalidate = useInvalidator();
  return useMutation({
    mutationFn: (id: string) => deletePolicy(id),
    onSuccess: () => invalidate([WARRANTY_POLICIES_KEY, WARRANTY_KINDS_KEY, WARRANTY_TERMS_KEY]),
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useSupersedePolicy() {
  const invalidate = useInvalidator();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: WarrantyPolicyWrite }) =>
      supersedePolicy(id, body),
    onSuccess: (result) => {
      invalidate([WARRANTY_POLICIES_KEY]);
      toast.success(
        `${result.created.version} published. ${result.closed.version} now ends ${result.closed.effective_to}.`,
      );
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

// ── Terms ───────────────────────────────────────────────────────────────────

export function useTermsGroupedByKind(policyId: string | null) {
  return useQuery({
    queryKey: [...WARRANTY_TERMS_KEY, policyId],
    queryFn: () => listTermsGroupedByKind(policyId!),
    enabled: !!policyId,
    retry: RETRY,
  });
}

export function useCreateTerm(policyId: string) {
  const invalidate = useInvalidator();
  return useMutation({
    mutationFn: (body: WarrantyTermWrite) => createTerm(policyId, body),
    onSuccess: () => {
      invalidate([WARRANTY_TERMS_KEY, WARRANTY_KINDS_KEY, WARRANTY_POLICIES_KEY]);
      toast.success('Term added');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useUpdateTerm(policyId: string) {
  const invalidate = useInvalidator();
  return useMutation({
    mutationFn: ({ termId, body }: { termId: string; body: WarrantyTermWrite }) =>
      updateTerm(policyId, termId, body),
    onSuccess: () => {
      invalidate([WARRANTY_TERMS_KEY, WARRANTY_KINDS_KEY, WARRANTY_POLICIES_KEY]);
      toast.success('Term updated');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useDeleteTerm(policyId: string) {
  const invalidate = useInvalidator();
  return useMutation({
    mutationFn: (termId: string) => deleteTerm(policyId, termId),
    onSuccess: () =>
      invalidate([WARRANTY_TERMS_KEY, WARRANTY_KINDS_KEY, WARRANTY_POLICIES_KEY]),
    onError: (e: Error) => toast.error(e.message),
  });
}

// ── Kinds ───────────────────────────────────────────────────────────────────

export function useKinds(searchQuery: string) {
  return useQuery({
    queryKey: [...WARRANTY_KINDS_KEY, searchQuery],
    queryFn: () => listKinds(searchQuery),
    retry: RETRY,
  });
}

export function useKindOptions() {
  return useQuery({
    queryKey: [...WARRANTY_KINDS_KEY, 'select'],
    queryFn: () => listKindOptions(),
    staleTime: 5 * 60 * 1000,
  });
}

export function useCreateKind() {
  const invalidate = useInvalidator();
  return useMutation({
    mutationFn: (body: WarrantyKindWrite) => createKind(body),
    onSuccess: () => {
      invalidate([WARRANTY_KINDS_KEY]);
      toast.success('Kind created');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useUpdateKind() {
  const invalidate = useInvalidator();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: WarrantyKindWrite }) => updateKind(id, body),
    onSuccess: () => {
      invalidate([WARRANTY_KINDS_KEY, WARRANTY_KIND_RULES_KEY, WARRANTY_TERMS_KEY]);
      toast.success('Kind updated');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useDeleteKind() {
  const invalidate = useInvalidator();
  return useMutation({
    mutationFn: (id: string) => deleteKind(id),
    onSuccess: () => invalidate([WARRANTY_KINDS_KEY]),
    onError: (e: Error) => toast.error(e.message),
  });
}

// ── Kind rules ──────────────────────────────────────────────────────────────

export function useKindRules(kindId: string | null) {
  return useQuery({
    queryKey: [...WARRANTY_KIND_RULES_KEY, kindId ?? 'all'],
    queryFn: () => listKindRules(kindId),
    retry: RETRY,
  });
}

export function useCreateKindRule() {
  const invalidate = useInvalidator();
  return useMutation({
    mutationFn: (body: WarrantyKindRuleWrite) => createKindRule(body),
    onSuccess: () => {
      invalidate([WARRANTY_KIND_RULES_KEY, WARRANTY_KINDS_KEY]);
      toast.success('Rule created');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useUpdateKindRule() {
  const invalidate = useInvalidator();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: WarrantyKindRuleUpdate }) =>
      updateKindRule(id, body),
    onSuccess: () => {
      invalidate([WARRANTY_KIND_RULES_KEY, WARRANTY_KINDS_KEY]);
      toast.success('Rule updated');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useDeleteKindRule() {
  const invalidate = useInvalidator();
  return useMutation({
    mutationFn: (id: string) => deleteKindRule(id),
    onSuccess: () => invalidate([WARRANTY_KIND_RULES_KEY, WARRANTY_KINDS_KEY]),
    onError: (e: Error) => toast.error(e.message),
  });
}

/** The tester. A mutation, not a query: it is a POST with a body and no cache. */
export function useTestKindRules() {
  return useMutation({
    mutationFn: (body: KindRuleTestRequest) => testKindRules(body),
  });
}

// ── Defect types ────────────────────────────────────────────────────────────

export function useDefectTypes() {
  return useQuery({
    queryKey: ['warranty-defect-types'],
    queryFn: () => listDefectTypes(),
    staleTime: 5 * 60 * 1000,
  });
}
