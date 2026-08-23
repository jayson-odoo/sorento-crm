import { useMutation, useQuery } from '@tanstack/react-query';

import {
  getProviderModels,
  testProviderModel,
  type ProviderModelsResult,
} from '@/services/providerModelService';

/**
 * The model list for one provider, asked of the provider itself.
 *
 * Shared rather than per-page: the assistant settings, the per-agent model card
 * and the chatbot media settings all pick a model, and three copies of a
 * hardcoded list is what let a retired model sit in one of them unnoticed.
 *
 * An empty `provider` is passed through rather than skipped - the backend reads
 * it as "inherit the assistant's provider" and answers for that one, which is
 * what the media page's blank provider actually runs on.
 */
export const providerModelsKey = (provider: string) => [
  'provider-models',
  provider || 'inherit',
];

export function useProviderModels(provider: string) {
  return useQuery<ProviderModelsResult>({
    queryKey: providerModelsKey(provider),
    queryFn: () => getProviderModels(provider),
    // The backend caches for an hour; this only stops a re-render refetching.
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });
}

/**
 * One real call on one model. Not `useQuery`: it costs tokens, so it happens
 * when an operator asks and never on render.
 */
export function useTestProviderModel() {
  return useMutation({
    mutationFn: ({
      provider,
      model,
      withImage,
    }: {
      provider: string;
      model: string;
      withImage?: boolean;
    }) => testProviderModel(provider, model, withImage ?? false),
  });
}
