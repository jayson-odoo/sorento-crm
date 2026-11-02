'use client';

import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import type { CoverDesign } from '@/lib/quotation-cover';
import { toast } from '@/lib/toast';
import {
  activateQuotationTemplate,
  createQuotationTemplate,
  deactivateQuotationTemplate,
  listMergeFields,
  listQuotationTemplates,
  previewCoverDesign,
  updateQuotationTemplate,
  type QuotationTemplateBody,
  type QuotationTemplateKind,
} from '../services/quotationTemplateService';

const TEMPLATES_KEY = 'project-quotation-templates';

export const quotationTemplatesKey = (kind: QuotationTemplateKind) => [TEMPLATES_KEY, kind];

export function useQuotationTemplates(kind: QuotationTemplateKind) {
  return useQuery({
    queryKey: quotationTemplatesKey(kind),
    queryFn: () => listQuotationTemplates(kind),
  });
}

/** The merge fields the intro and closing text may use, served by the backend registry. */
export function useQuotationMergeFields() {
  return useQuery({
    queryKey: [TEMPLATES_KEY, 'merge-fields'],
    queryFn: listMergeFields,
    staleTime: 5 * 60_000,
  });
}

/** The designer's live preview. Settled for 400 ms so typing does not request per keystroke. */
export function useCoverDesignPreview(design: CoverDesign, bodyHtml: string) {
  const settled = useDebouncedValue({ design, body_html: bodyHtml }, 400);
  return useQuery({
    queryKey: [TEMPLATES_KEY, 'cover-preview', settled],
    queryFn: () => previewCoverDesign(settled),
    placeholderData: keepPreviousData,
  });
}

export function useQuotationTemplateMutations(kind: QuotationTemplateKind) {
  const queryClient = useQueryClient();
  const invalidate = () => queryClient.invalidateQueries({ queryKey: [TEMPLATES_KEY] });

  const create = useMutation({
    mutationFn: (body: QuotationTemplateBody) => createQuotationTemplate(kind, body),
    onSuccess: () => {
      invalidate();
      toast.success('Template created');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<QuotationTemplateBody> }) =>
      updateQuotationTemplate(id, body),
    onSuccess: () => {
      invalidate();
      toast.success('Template saved');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const activate = useMutation({
    mutationFn: (id: string) => activateQuotationTemplate(id),
    onSuccess: () => {
      invalidate();
      toast.success('Template activated');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const deactivate = useMutation({
    mutationFn: (id: string) => deactivateQuotationTemplate(id),
    onSuccess: () => {
      invalidate();
      toast.success('Template deactivated');
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return { create, update, activate, deactivate };
}
