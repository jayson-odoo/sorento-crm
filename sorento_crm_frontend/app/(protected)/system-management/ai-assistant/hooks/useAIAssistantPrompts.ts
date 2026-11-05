'use client';

import { useMutation, useQuery, useQueryClient, type QueryKey } from '@tanstack/react-query';
import type { ListPagerParams, ListPagerPage } from '@/hooks/useListPager';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';
import { splitMulti } from '@/lib/list-filters/multiValue';
import {
  dryRunPrompt,
  getPromptArchitecture,
  getPromptVersion,
  getPromptList,
  getPromptVersions,
  getRegistryVariables,
  listPromptKeys,
  saveVersion,
  setAgentModel,
  setLabel,
  type DryRunPayload,
  type PromptListParams,
  type SaveVersionPayload,
  type SetAgentModelPayload,
  type SetLabelPayload,
} from '../services/aiPromptsService';

const KEYS = ['ai-prompts'] as const;
const versionsKey = (name: string) => ['ai-prompts', name, 'versions'];
const versionKey = (name: string, v: number) => ['ai-prompts', name, 'version', v];

export function usePromptKeys() {
  return useQuery({ queryKey: KEYS, queryFn: listPromptKeys });
}

/**
 * The prompts list's React Query key. Under `ai-prompts`, so a save, publish or model change
 * (which invalidate that prefix) refreshes the list too. The detail page's pager rebuilds the
 * SAME key from the URL, so it walks the page the list already fetched.
 */
export function promptListQueryKey(params: PromptListParams): QueryKey {
  return [
    ...KEYS,
    'list',
    params.pageIndex,
    params.pageSize,
    params.sorting,
    params.searchQuery,
    params.status ?? [],
    params.model ?? [],
  ];
}

/** The list query a detail URL describes: the filters ride comma-joined, like the list writes them. */
export function promptListParamsFromUrl(params: ListPagerParams): PromptListParams {
  return {
    pageIndex: params.pageIndex,
    pageSize: params.pageSize,
    sorting: params.sorting,
    searchQuery: params.searchQuery,
    status: splitMulti(params.filters.status),
    model: splitMulti(params.filters.model),
  };
}

/** The record pager's two hooks into the prompts list. */
export const promptsPagerQuery = {
  listQueryKey: (params: ListPagerParams): QueryKey => promptListQueryKey(promptListParamsFromUrl(params)),
  fetchPage: (params: ListPagerParams): Promise<ListPagerPage> => getPromptList(promptListParamsFromUrl(params)),
};

export function usePromptList(params: PromptListParams) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: promptListQueryKey(params),
    queryFn: () => getPromptList(params),
  });
}

export function usePromptVersions(name: string) {
  return useQuery({
    queryKey: versionsKey(name),
    queryFn: () => getPromptVersions(name),
    enabled: !!name,
  });
}

export function usePromptVersion(name: string, version: number | null) {
  return useQuery({
    queryKey: versionKey(name, version ?? -1),
    queryFn: () => getPromptVersion(name, version as number),
    enabled: !!name && version != null,
  });
}

export function usePromptArchitecture(name: string, version: number | null, enabled: boolean) {
  return useQuery({
    queryKey: ['ai-prompts', name, 'architecture', version ?? -1],
    queryFn: () => getPromptArchitecture(name, version as number),
    enabled: !!name && version != null && enabled,
  });
}

export function useSaveVersion(name: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: SaveVersionPayload) => saveVersion(name, payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: versionsKey(name) });
      void qc.invalidateQueries({ queryKey: KEYS });
    },
  });
}

export function useSetLabel(name: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: SetLabelPayload) => setLabel(name, payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: versionsKey(name) });
      void qc.invalidateQueries({ queryKey: KEYS });
    },
  });
}

/** Point one agent at one LLM. Invalidates the key list so the table reflects it. */
export function useSetAgentModel(name: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: SetAgentModelPayload) => setAgentModel(name, payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: KEYS });
    },
  });
}

export function useDryRun(name: string) {
  return useMutation({
    mutationFn: (payload: DryRunPayload) => dryRunPrompt(name, payload),
  });
}

/** The key's registry variables with their live text (R5a chips + wired panel). */
export function useRegistryVariables(name: string, enabled: boolean) {
  return useQuery({
    queryKey: ['ai-prompts', name, 'registry-variables'],
    queryFn: () => getRegistryVariables(name),
    enabled: !!name && enabled,
    staleTime: 30_000,
  });
}
