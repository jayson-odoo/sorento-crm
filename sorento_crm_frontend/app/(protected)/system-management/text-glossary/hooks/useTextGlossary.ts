'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import {
  deleteTextGlossaryEntry,
  listTextGlossary,
  upsertTextGlossaryEntry,
} from '../services/textGlossaryService';
import type { TextGlossaryUpsertBody } from '../types/textGlossary.types';

export const TEXT_GLOSSARY_LIST_KEY = ['system', 'text-glossary'] as const;

export function useTextGlossary(query: string) {
  return useQuery({
    queryKey: [...TEXT_GLOSSARY_LIST_KEY, query],
    queryFn: () => listTextGlossary(query),
  });
}

/** Add mapping AND row edit (R2) - one write path, PUT upserts either way. */
export function useUpsertTextGlossary() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: TextGlossaryUpsertBody) => upsertTextGlossaryEntry(body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: TEXT_GLOSSARY_LIST_KEY });
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

/** No mutation hook for delete: the row's action parks `text_glossary.forget` as a
 *  pending action (`useDeferredRowAction`, AC-E4) and the SERVER deletes it when the
 *  window lapses. `deleteTextGlossaryEntry` stays as the immediate route behind that
 *  action, re-exported so the list never imports the service directly. */
export { deleteTextGlossaryEntry };
