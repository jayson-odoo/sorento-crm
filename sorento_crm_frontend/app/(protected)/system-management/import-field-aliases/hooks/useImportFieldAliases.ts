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

/** No mutation hook for delete, and no direct service call from the list either: the
 *  chip's × parks `import_field_alias.forget` on the server (`useDeferredRowAction`,
 *  AC-E3), and the SERVER deletes the row when the window lapses. `deleteImportFieldAlias`
 *  stays as the immediate route behind that action, and is what a caller with no window
 *  would use. */
export { deleteImportFieldAlias };

export function importFieldAliasListQueryKey(docType: ImportFieldAliasDocType) {
  return [...KEY, 'list', docType] as const;
}
