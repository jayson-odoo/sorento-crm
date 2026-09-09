'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import {
  createImportFieldAlias,
  deleteImportFieldAlias,
  listImportFieldAliasFields,
  listImportFieldAliases,
} from '../services/importFieldAliasService';
import type { ImportFieldAliasDocType } from '../types/importFieldAlias.types';

const KEY = ['system', 'import-field-aliases'] as const;

export function useImportFieldAliases(docType: ImportFieldAliasDocType) {
  return useQuery({
    queryKey: [...KEY, 'list', docType],
    queryFn: () => listImportFieldAliases(docType),
  });
}

export function useImportFieldAliasFields(docType: ImportFieldAliasDocType) {
  return useQuery({
    queryKey: [...KEY, 'fields', docType],
    queryFn: () => listImportFieldAliasFields(docType),
  });
}

export function useCreateImportFieldAlias(docType: ImportFieldAliasDocType) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { field: string; alias: string; locale?: string | null }) =>
      createImportFieldAlias({ doc_type: docType, ...data }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: [...KEY, 'list', docType] });
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

/** No mutation hook for delete: the chip's × is a deferred action (AC-E3) driven by
 *  `useMockDeferredWindow` (Phase 1) - see `ImportFieldAliasesList.tsx`. `deleteImportFieldAlias`
 *  itself is called directly from there once the window lapses. */
export { deleteImportFieldAlias };

export function importFieldAliasListQueryKey(docType: ImportFieldAliasDocType) {
  return [...KEY, 'list', docType] as const;
}
