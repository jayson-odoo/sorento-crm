'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  createEmailTemplate,
  getEmailTemplate,
  getEmailTemplates,
  getTemplateVariableCatalog,
  previewEmailTemplate,
  updateEmailTemplate,
} from '../services/emailTemplateService';
import type {
  EmailTemplateCreateBody,
  EmailTemplateUpdateBody,
} from '../types/emailTemplate.types';

export function useEmailTemplates(params: { page?: number; limit?: number; query?: string } = {}) {
  return useQuery({
    queryKey: ['email-templates', params],
    queryFn: () => getEmailTemplates(params),
    staleTime: 1000 * 60,
  });
}

export function useEmailTemplate(id: string | null) {
  return useQuery({
    queryKey: ['email-template', id],
    queryFn: () => getEmailTemplate(id!),
    enabled: !!id,
  });
}

export function useTemplateVariableCatalog() {
  return useQuery({
    queryKey: ['email-template-variable-catalog'],
    queryFn: getTemplateVariableCatalog,
    staleTime: 1000 * 60 * 30,
  });
}

export function useCreateEmailTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: EmailTemplateCreateBody) => createEmailTemplate(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['email-templates'] }),
  });
}

export function useUpdateEmailTemplate(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: EmailTemplateUpdateBody) => updateEmailTemplate(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['email-templates'] });
      qc.invalidateQueries({ queryKey: ['email-template', id] });
    },
  });
}

export function usePreviewEmailTemplate(id: string | null) {
  return useMutation({
    mutationFn: (context?: Record<string, unknown>) => previewEmailTemplate(id!, context),
  });
}
