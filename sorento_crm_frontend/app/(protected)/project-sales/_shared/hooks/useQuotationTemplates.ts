'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import {
  activateQuotationTemplate,
  createQuotationTemplate,
  listQuotationTemplates,
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

  return { create, update, activate };
}
