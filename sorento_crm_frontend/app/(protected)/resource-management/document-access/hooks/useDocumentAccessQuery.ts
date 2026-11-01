import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';
import { toast } from '@/lib/toast';
import { updateAttachmentType } from '../../attachment-types/services/attachmentTypeService';
import { updateAttachment } from '../../attachments/services/attachmentService';
import { getDocumentAccess, getDocumentAccessDocuments } from '../services/documentAccessService';
import type { DocumentAccessRow } from '../types/documentAccess.types';

const KEY = 'document-access';

export function useDocumentAccessQuery(contactId?: string) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: [KEY, 'matrix', contactId ?? null],
    queryFn: () => getDocumentAccess({ contactId }),
  });
}

export function useDocumentAccessDocuments(typeId: string | null, contactId: string | undefined, page: number, limit: number) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: [KEY, 'documents', typeId, contactId ?? null, page, limit],
    queryFn: () => getDocumentAccessDocuments(typeId as string, { contactId, page, limit }),
    enabled: Boolean(typeId),
  });
}

function countText(n: number) {
  return `${n} document${n === 1 ? '' : 's'}`;
}

function messageOf(error: unknown, fallback: string) {
  return error instanceof Error && error.message ? error.message : fallback;
}

export interface TickInput {
  row: DocumentAccessRow;
  /** The access type ticked, or null for the Staff tick. */
  code: string | null;
  name: string;
  on: boolean;
  /** Every active code in catalogue order: the saved list is built in this order. */
  catalogue: string[];
}

/** Ticks, the Direct access switch and a document's levels. Each saves at once and says what it did. */
export function useDocumentAccessMutations() {
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: [KEY] });

  const tick = useMutation({
    mutationFn: ({ row, code, on, catalogue }: TickInput) => {
      if (code === null) return updateAttachmentType(row.id, { ai_read_staff: on });
      const next = new Set(row.ai_read_codes);
      if (on) next.add(code);
      else next.delete(code);
      return updateAttachmentType(row.id, { ai_read_codes: catalogue.filter((c) => next.has(c)) });
    },
    onSuccess: (_data, { row, code, name, on }) => {
      const n = code === null ? row.readable_count : (row.reach[code] ?? 0);
      toast.success(`${row.type_name}: ${name} ${on ? 'can now read' : 'no longer reads'} ${countText(n)}.`);
      void refresh();
    },
    onError: (error) => toast.error(messageOf(error, 'The tick could not be saved.')),
  });

  const direct = useMutation({
    mutationFn: ({ row, on }: { row: DocumentAccessRow; on: boolean }) =>
      updateAttachmentType(row.id, { is_direct_access: on }),
    onSuccess: (_data, { row, on }) => {
      toast.success(`${row.type_name}: Direct access ${on ? 'on' : 'off'}.`);
      void refresh();
    },
    onError: (error) => toast.error(messageOf(error, 'Direct access could not be saved.')),
  });

  const levels = useMutation({
    mutationFn: ({ id, accessLevels }: { id: string; accessLevels: string[] }) =>
      updateAttachment(id, { access_levels: accessLevels }),
    onSuccess: () => void refresh(),
    onError: (error) => toast.error(messageOf(error, 'The access levels could not be saved.')),
  });

  return { tick, direct, levels };
}
