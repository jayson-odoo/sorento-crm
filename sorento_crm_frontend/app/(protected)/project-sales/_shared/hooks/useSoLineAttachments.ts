'use client';

import { useMemo } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import {
  lookupSoLineAttachments,
  uploadSoLineAttachments,
  type AttachmentTargetKind,
  type SoLineAttachmentsByLine,
} from '../services/soLineAttachmentService';

/**
 * #1312 (PLAN-oi-line-attachments-27sep.md): the board and the OI Lines tab both
 * batch every visible line into ONE lookup call, so this prefix is what a completed
 * upload or deferred delete invalidates.
 */
export const SO_LINE_ATTACHMENTS_KEY = ['project-sales', 'so-line-attachments'] as const;

const EMPTY: SoLineAttachmentsByLine = {};

/** One lookup call for a whole grid's worth of core line ids (AC-U2) - never one per
 * row. `lineIds` is de-duplicated and order-independent, so a caller re-rendering with
 * the same set in a different order does not refetch. */
export function useSoLineAttachmentLookup(
  lineIds: (string | null | undefined)[],
  kind: AttachmentTargetKind = 'sales_order_line',
) {
  const ids = useMemo(
    () => Array.from(new Set(lineIds.filter((id): id is string => Boolean(id)))).sort(),
    [lineIds],
  );
  const query = useQuery({
    // The sales-order-line key stays exactly as it was; an OI row lookup adds its kind.
    queryKey:
      kind === 'sales_order_line'
        ? [...SO_LINE_ATTACHMENTS_KEY, ids]
        : [...SO_LINE_ATTACHMENTS_KEY, kind, ids],
    queryFn: () => lookupSoLineAttachments(ids, kind),
    enabled: ids.length > 0,
  });
  return { ...query, data: query.data ?? EMPTY };
}

export function useUploadSoLineAttachments() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      lineId,
      files,
      kind = 'sales_order_line',
    }: {
      lineId: string;
      files: File[];
      kind?: AttachmentTargetKind;
    }) =>
      kind === 'sales_order_line'
        ? uploadSoLineAttachments(lineId, files)
        : uploadSoLineAttachments(lineId, files, kind),
    onSuccess: (_attachments, variables) => {
      toast.success(
        variables.files.length === 1 ? 'File added' : `${variables.files.length} files added`,
      );
    },
    onError: (e: Error) => toast.error(e.message),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: SO_LINE_ATTACHMENTS_KEY });
    },
  });
}
