'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import {
  createIntegration,
  getIntegration,
  getIntegrations,
  issueKey,
  rotateKey,
  updateIntegration,
} from '../services/integrationService';
import type {
  Integration,
  IntegrationCreatePayload,
  IntegrationUpdatePayload,
  IssuedKey,
} from '../types/integration.types';

const LIST_KEY = ['integrations'];

export function useIntegrations() {
  return useQuery<Integration[]>({
    queryKey: LIST_KEY,
    queryFn: getIntegrations,
  });
}

export function useIntegration(id: string) {
  return useQuery<Integration>({
    queryKey: ['integration', id],
    queryFn: () => getIntegration(id),
    enabled: !!id,
  });
}

export function useCreateIntegration() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: IntegrationCreatePayload) => createIntegration(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: LIST_KEY });
      toast.success('Integration created');
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

export function useUpdateIntegration() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: IntegrationUpdatePayload }) =>
      updateIntegration(id, payload),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: LIST_KEY });
      queryClient.invalidateQueries({ queryKey: ['integration', variables.id] });
      toast.success('Integration updated');
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

/**
 * Issuing and rotating return a plaintext key that exists nowhere else.
 *
 * The caller is responsible for putting it in front of the user immediately.
 * Deliberately no toast carrying the value, and nothing here writes it to
 * storage: a secret that reaches a log or localStorage has escaped, and the
 * only remedy would be another rotation.
 */
export function useIssueKey() {
  const queryClient = useQueryClient();
  return useMutation<IssuedKey, Error, string>({
    mutationFn: (integrationId: string) => issueKey(integrationId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: LIST_KEY }),
    onError: (error: Error) => toast.error(error.message),
  });
}

export function useRotateKey() {
  const queryClient = useQueryClient();
  return useMutation<IssuedKey, Error, { integrationId: string; graceDays: number }>({
    mutationFn: ({ integrationId, graceDays }) => rotateKey(integrationId, graceDays),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: LIST_KEY }),
    onError: (error: Error) => toast.error(error.message),
  });
}

