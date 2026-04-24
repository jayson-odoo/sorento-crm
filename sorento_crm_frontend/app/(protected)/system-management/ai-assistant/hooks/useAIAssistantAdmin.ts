'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  getAIAssistantConfig,
  getAIAssistantTools,
  updateAIAssistantConfig,
  type AIAssistantConfigUpdatePayload,
} from '../services/aiAssistantAdminService';

const KEY = ['system-ai-assistant-config'];
const TOOLS_KEY = ['system-ai-assistant-tools'];

export function useAIAssistantConfig() {
  return useQuery({
    queryKey: KEY,
    queryFn: getAIAssistantConfig,
  });
}

export function useUpdateAIAssistantConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: AIAssistantConfigUpdatePayload) => updateAIAssistantConfig(payload),
    onSuccess: () => void qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useAIAssistantTools() {
  return useQuery({
    queryKey: TOOLS_KEY,
    queryFn: getAIAssistantTools,
    staleTime: 60 * 1000,
  });
}
