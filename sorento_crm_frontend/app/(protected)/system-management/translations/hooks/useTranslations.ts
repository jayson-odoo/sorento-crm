'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';

import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';

import {
  listTranslations,
  updateTranslation,
  type TranslationListQuery,
} from '../services/translationService';
import type { TranslationUpdateBody } from '../types/translation.types';

export const TRANSLATIONS_LIST_KEY = ['translations'] as const;

export function useTranslations(query: TranslationListQuery) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: [...TRANSLATIONS_LIST_KEY, query],
    queryFn: () => listTranslations(query),
    retry: 1,
  });
}

export function useUpdateTranslation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: TranslationUpdateBody }) =>
      updateTranslation(id, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: TRANSLATIONS_LIST_KEY });
      toast.success('Translation updated');
    },
    onError: (error: Error) => toast.error(error.message),
  });
}
