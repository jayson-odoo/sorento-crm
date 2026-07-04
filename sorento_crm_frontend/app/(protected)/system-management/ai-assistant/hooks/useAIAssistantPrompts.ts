'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  dryRunPrompt,
  getPromptVersion,
  getPromptVersions,
  listPromptKeys,
  saveVersion,
  setLabel,
  type DryRunPayload,
  type SaveVersionPayload,
  type SetLabelPayload,
} from '../services/aiPromptsService';

const KEYS = ['ai-prompts'] as const;
const versionsKey = (name: string) => ['ai-prompts', name, 'versions'];
const versionKey = (name: string, v: number) => ['ai-prompts', name, 'version', v];

export function usePromptKeys() {
  return useQuery({ queryKey: KEYS, queryFn: listPromptKeys });
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

export function useDryRun(name: string) {
  return useMutation({
    mutationFn: (payload: DryRunPayload) => dryRunPrompt(name, payload),
  });
}
