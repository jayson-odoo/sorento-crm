import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { SortingState } from '@tanstack/react-table';
import { toast } from '@/lib/toast';
import { postListQuerySearch } from '@/lib/list-query/listQueryService';
import type { ListQueryFilterGroup } from '@/lib/list-query/listQueryService';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';
import {
  applyWorkflowTransition,
  createWorkflowDefinition,
  createWorkflowSubmission,
  fetchAllowedTransitions,
  fetchWorkflowDefinition,
  fetchPublishedWorkflowDefinitionsForSubmission,
  fetchWorkflowDefinitions,
  fetchWorkflowFlowGraph,
  fetchWorkflowSubmission,
  fetchWorkflowSubmissions,
  publishWorkflowDefinition,
  updateWorkflowDefinition,
  updateWorkflowSubmission,
} from '../services/workflowFormsService';
import type {
  WorkflowFormDefinition,
  WorkflowFormSchema,
  WorkflowSubmission,
} from '../types/workflowForms.types';

export const wfKeys = {
  definitions: ['workflow-forms', 'definitions'] as const,
  publishedForSubmission: ['workflow-forms', 'published-for-submission'] as const,
  definition: (id: string) => ['workflow-forms', 'definition', id] as const,
  submissions: ['workflow-forms', 'submissions'] as const,
  submission: (id: string) => ['workflow-forms', 'submission', id] as const,
  allowedTransitions: (id: string) => ['workflow-forms', 'allowed-transitions', id] as const,
  flowGraph: (id: string, source: string) => ['workflow-forms', 'flow-graph', id, source] as const,
};

export function useWorkflowDefinitionsQuery(params: { page?: number; limit?: number; q?: string }) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: [...wfKeys.definitions, params],
    queryFn: () => fetchWorkflowDefinitions({ page: params.page ?? 1, limit: params.limit ?? 50, q: params.q }),
  });
}

/** Data grid + list-query (filters / export). */
export function useWorkflowDefinitionsGridQuery(
  params: {
    pageIndex: number;
    pageSize: number;
    sorting: SortingState;
    searchQuery: string;
    advancedFilter: ListQueryFilterGroup | null;
    quickStatus: 'all' | 'active' | 'inactive';
  },
  options?: { enabled?: boolean },
) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: [
      ...wfKeys.definitions,
      'grid',
      params.pageIndex,
      params.pageSize,
      params.sorting,
      params.searchQuery,
      params.advancedFilter,
      params.quickStatus,
    ],
    queryFn: () =>
      postListQuerySearch<WorkflowFormDefinition>({
        resource: 'workflow_form_definitions',
        filter: params.advancedFilter ?? undefined,
        page: params.pageIndex + 1,
        limit: params.pageSize,
        sort: params.sorting[0]?.id || 'updated_at',
        dir: params.sorting[0]?.desc ? 'desc' : 'asc',
        quick_search: params.searchQuery || undefined,
        workflow_definition_is_active:
          params.quickStatus === 'all' ? undefined : params.quickStatus === 'active',
      }),
    enabled: options?.enabled !== false,
    staleTime: 30_000,
    retry: 1,
  });
}

/** Submissions grid + list-query. */
export function useWorkflowSubmissionsGridQuery(
  params: {
    pageIndex: number;
    pageSize: number;
    sorting: SortingState;
    searchQuery: string;
    advancedFilter: ListQueryFilterGroup | null;
    fixedDefinitionId?: string;
    scopeDefinitionId: string;
    quickStateCode: string;
  },
  options?: { enabled?: boolean },
) {
  const wfDef =
    params.fixedDefinitionId ||
    (params.scopeDefinitionId && params.scopeDefinitionId !== '__all'
      ? params.scopeDefinitionId
      : undefined);
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: [
      ...wfKeys.submissions,
      'grid',
      params.pageIndex,
      params.pageSize,
      params.sorting,
      params.searchQuery,
      params.advancedFilter,
      params.fixedDefinitionId,
      params.scopeDefinitionId,
      params.quickStateCode,
    ],
    queryFn: () =>
      postListQuerySearch<WorkflowSubmission>({
        resource: 'workflow_form_submissions',
        filter: params.advancedFilter ?? undefined,
        page: params.pageIndex + 1,
        limit: params.pageSize,
        sort: params.sorting[0]?.id || 'updated_at',
        dir: params.sorting[0]?.desc ? 'desc' : 'asc',
        quick_search: params.searchQuery || undefined,
        workflow_form_definition_id: wfDef,
        workflow_submission_state_code: params.quickStateCode.trim() || undefined,
      }),
    enabled: options?.enabled !== false,
    staleTime: 30_000,
    retry: 1,
  });
}

export function usePublishedWorkflowDefinitionsForSubmissionQuery(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: wfKeys.publishedForSubmission,
    queryFn: () => fetchPublishedWorkflowDefinitionsForSubmission(),
    enabled: options?.enabled !== false,
    staleTime: 60_000,
    retry: false,
  });
}

export function useWorkflowDefinitionQuery(id: string | null) {
  return useQuery({
    queryKey: wfKeys.definition(id || ''),
    queryFn: () => fetchWorkflowDefinition(id!),
    enabled: !!id,
  });
}

export function useWorkflowFlowGraphQuery(
  id: string | null,
  source: 'draft' | 'published' = 'draft',
  enabled: boolean = true,
) {
  return useQuery({
    queryKey: wfKeys.flowGraph(id || '', source),
    queryFn: () => fetchWorkflowFlowGraph(id!, source),
    enabled: !!id && enabled,
  });
}

export function useCreateWorkflowDefinition() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createWorkflowDefinition,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: wfKeys.definitions });
      toast.success('Workflow form created');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useUpdateWorkflowDefinition(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Parameters<typeof updateWorkflowDefinition>[1]) => updateWorkflowDefinition(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: wfKeys.definitions });
      qc.invalidateQueries({ queryKey: wfKeys.definition(id) });
      toast.success('Saved');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function usePublishWorkflowDefinition(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => publishWorkflowDefinition(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: wfKeys.definitions });
      qc.invalidateQueries({ queryKey: wfKeys.definition(id) });
      qc.invalidateQueries({ queryKey: wfKeys.publishedForSubmission });
      toast.success('Published new version');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useWorkflowSubmissionsQuery(params: {
  page?: number;
  limit?: number;
  definition_id?: string;
  state_code?: string;
}) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: [...wfKeys.submissions, params],
    queryFn: () =>
      fetchWorkflowSubmissions({
        page: params.page ?? 1,
        limit: params.limit ?? 50,
        definition_id: params.definition_id,
        state_code: params.state_code,
      }),
  });
}

export function useWorkflowSubmissionQuery(id: string | null) {
  return useQuery({
    queryKey: wfKeys.submission(id || ''),
    queryFn: () => fetchWorkflowSubmission(id!),
    enabled: !!id,
  });
}

export function useAllowedTransitionsQuery(submissionId: string | null) {
  return useQuery({
    queryKey: wfKeys.allowedTransitions(submissionId || ''),
    queryFn: () => fetchAllowedTransitions(submissionId!),
    enabled: !!submissionId,
    retry: 1,
  });
}

export function useCreateWorkflowSubmission() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createWorkflowSubmission,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: wfKeys.submissions });
      toast.success('Submission created');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useUpdateWorkflowSubmission(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Parameters<typeof updateWorkflowSubmission>[1]) => updateWorkflowSubmission(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: wfKeys.submissions });
      qc.invalidateQueries({ queryKey: wfKeys.submission(id) });
      toast.success('Saved');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useApplyWorkflowTransition(submissionId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { transition_id: string; remark?: string }) =>
      applyWorkflowTransition(submissionId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: wfKeys.submission(submissionId) });
      qc.invalidateQueries({ queryKey: wfKeys.allowedTransitions(submissionId) });
      qc.invalidateQueries({ queryKey: wfKeys.submissions });
      toast.success('State updated');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export type { WorkflowFormSchema };
