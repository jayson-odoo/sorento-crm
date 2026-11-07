'use client';

import { useCallback } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useDeferredRowAction } from '@/hooks/useDeferredRowAction';
import {
  createAccessoryTemplate,
  findAccessoryTemplate,
  getAccessoryTemplate,
  getAccessoryTemplateUsage,
  listAccessoryTemplates,
  updateAccessoryTemplate,
  type AccessoryTemplateInput,
} from '../../services/accessoryTemplateService';

export const ACCESSORY_TEMPLATES_QUERY_KEY = 'dealer-kit-accessory-templates';

export function useAccessoryTemplatesQuery() {
  return useQuery({
    queryKey: [ACCESSORY_TEMPLATES_QUERY_KEY],
    queryFn: listAccessoryTemplates,
  });
}

export function useAccessoryTemplateQuery(id: string | null | undefined) {
  return useQuery({
    queryKey: [ACCESSORY_TEMPLATES_QUERY_KEY, 'one', id],
    queryFn: () => getAccessoryTemplate(id as string),
    enabled: Boolean(id),
  });
}

/** Reads one template fresh (never from cache); null when it is gone. For the live link's pre-push check. */
export function useFetchAccessoryTemplate() {
  const queryClient = useQueryClient();
  return useCallback(
    (id: string) =>
      queryClient.fetchQuery({
        queryKey: [ACCESSORY_TEMPLATES_QUERY_KEY, 'fresh', id],
        queryFn: () => findAccessoryTemplate(id),
        staleTime: 0,
      }),
    [queryClient],
  );
}

/** Usage counts change when a tag template gains or loses a linked box. */
export function useRefreshAccessoryTemplates() {
  const queryClient = useQueryClient();
  return useCallback(
    () => queryClient.invalidateQueries({ queryKey: [ACCESSORY_TEMPLATES_QUERY_KEY] }),
    [queryClient],
  );
}

export function useAccessoryTemplateUsage(id: string | null | undefined, enabled = true) {
  return useQuery({
    queryKey: [ACCESSORY_TEMPLATES_QUERY_KEY, 'usage', id],
    queryFn: () => getAccessoryTemplateUsage(id as string),
    enabled: Boolean(id) && enabled,
  });
}

export function useCreateAccessoryTemplate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: AccessoryTemplateInput) => createAccessoryTemplate(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [ACCESSORY_TEMPLATES_QUERY_KEY] });
    },
  });
}

export function useUpdateAccessoryTemplate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: Partial<AccessoryTemplateInput> }) =>
      updateAccessoryTemplate(id, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [ACCESSORY_TEMPLATES_QUERY_KEY] });
    },
  });
}

/** Delete = deferred action, no confirm dialog: the server commits `accessory_box_preset.delete`. */
export function useDeleteAccessoryTemplate() {
  return useDeferredRowAction({
    actionKey: 'accessory_box_preset.delete',
    entityType: 'accessory_box_preset',
    successMessage: 'Accessories template deleted',
    invalidateKeys: [[ACCESSORY_TEMPLATES_QUERY_KEY]],
  });
}
