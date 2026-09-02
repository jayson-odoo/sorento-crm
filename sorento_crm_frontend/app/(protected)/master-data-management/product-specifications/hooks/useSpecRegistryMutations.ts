'use client';

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { createSpecKey, rereadCatalogue } from '../services/productSpecService';
import type { SpecRegistryKey } from '../types/productSpec.types';
import { CATALOGUE_STATUS_QUERY_KEY } from './useCatalogueStatusQuery';
import { SPEC_REGISTRY_QUERY_KEY } from './useSpecRegistryQuery';

/**
 * The registry-list mutations Group A needs: create a specification, and start a
 * catalogue reread. `update` / `delete` / `addValue` land with the record page (S2),
 * which is the only screen that offers them.
 */
export function useSpecRegistryMutations() {
  const queryClient = useQueryClient();

  const create = useMutation<SpecRegistryKey, Error, Parameters<typeof createSpecKey>[0]>({
    mutationFn: (body) => createSpecKey(body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: SPEC_REGISTRY_QUERY_KEY });
    },
    onError: (error) => {
      toast.error(error.message || 'Failed to create the specification');
    },
  });

  const reread = useMutation<{ status: string }, Error, void>({
    mutationFn: () => rereadCatalogue(),
    onSuccess: () => {
      toast.success('Reading the catalogue again');
      queryClient.invalidateQueries({ queryKey: CATALOGUE_STATUS_QUERY_KEY });
    },
    onError: (error) => {
      toast.error(error.message || 'Could not start reading the catalogue');
    },
  });

  return { create, reread };
}
