'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  createAutomation,
  deleteAutomation,
  getAutomation,
  getAutomationRuns,
  getAutomations,
  getTriggerCatalog,
  runAutomationNow,
  toggleAutomation,
  updateAutomation,
} from '../services/automationService';
import type {
  AutomationCreateBody,
  AutomationUpdateBody,
} from '../types/automation.types';

export function useAutomations(params: { page?: number; limit?: number; query?: string } = {}) {
  return useQuery({
    queryKey: ['automations', params],
    queryFn: () => getAutomations(params),
    staleTime: 1000 * 30,
  });
}

export function useAutomation(id: string | null) {
  return useQuery({
    queryKey: ['automation', id],
    queryFn: () => getAutomation(id!),
    enabled: !!id,
  });
}

export function useTriggerCatalog() {
  return useQuery({
    queryKey: ['automation-triggers'],
    queryFn: getTriggerCatalog,
    staleTime: 1000 * 60 * 30,
  });
}

export function useCreateAutomation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: AutomationCreateBody) => createAutomation(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['automations'] }),
  });
}

export function useUpdateAutomation(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: AutomationUpdateBody) => updateAutomation(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['automations'] });
      qc.invalidateQueries({ queryKey: ['automation', id] });
    },
  });
}

export function useToggleAutomation(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (enabled: boolean) => toggleAutomation(id, enabled),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['automations'] });
      qc.invalidateQueries({ queryKey: ['automation', id] });
    },
  });
}

export function useDeleteAutomation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteAutomation(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['automations'] }),
  });
}

export function useRunAutomationNow(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => runAutomationNow(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['automations'] });
      qc.invalidateQueries({ queryKey: ['automation', id] });
      qc.invalidateQueries({ queryKey: ['automation-runs', id] });
    },
  });
}

export function useAutomationRuns(id: string | null, page = 1, limit = 50) {
  return useQuery({
    queryKey: ['automation-runs', id, page, limit],
    queryFn: () => getAutomationRuns(id!, page, limit),
    enabled: !!id,
    staleTime: 1000 * 15,
  });
}
