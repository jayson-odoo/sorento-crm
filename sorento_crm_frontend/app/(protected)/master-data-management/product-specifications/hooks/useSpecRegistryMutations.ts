'use client';

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import {
  createSpecKey,
  rereadCatalogue,
  updateSpecKey,
} from '../services/productSpecService';
import type { SpecRegistryKey } from '../types/productSpec.types';
import { CATALOGUE_STATUS_QUERY_KEY } from './useCatalogueStatusQuery';
import { SPEC_REGISTRY_QUERY_KEY } from './useSpecRegistryQuery';

/**
 * The registry mutations both routes need: create and reread from the list (S1),
 * update from the record page (S2). `update` is the low-level PATCH -
 * `useSpecKeyRecord` is what turns an edit session's draft into the one call B.2
 * promises.
 *
 * No `delete` here: B.6 runs Delete through the deferred-action engine
 * (`hooks/useDeferredAction`), the same pattern every other record's gear uses -
 * see `actions.tsx`. `deleteSpecKey` in the service stays for the day a backend
 * `spec_key.delete` action handler wraps it.
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

  const update = useMutation<
    SpecRegistryKey,
    Error,
    { specKey: string; body: Parameters<typeof updateSpecKey>[1] }
  >({
    mutationFn: ({ specKey, body }) => updateSpecKey(specKey, body),
    // No `invalidateQueries` here, deliberately: `useSpecKeyRecord.save()` writes the
    // registry cache itself with the PATCH response, in the same call. An invalidate
    // here would race that write with a background refetch of the same data.
    onError: (error) => {
      toast.error(error.message || 'Failed to save the specification', {
        duration: 10_000,
      });
    },
  });

  return { create, reread, update };
}
