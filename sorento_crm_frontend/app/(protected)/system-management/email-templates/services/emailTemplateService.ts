import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type {
  EmailTemplate,
  EmailTemplateCreateBody,
  EmailTemplatePreview,
  EmailTemplateUpdateBody,
  ListResponse,
  TemplateVariable,
} from '../types/emailTemplate.types';

export async function getEmailTemplates(
  params: { page?: number; limit?: number; query?: string } = {},
): Promise<ListResponse<EmailTemplate>> {
  const sp = new URLSearchParams();
  sp.set('page', String(params.page ?? 1));
  sp.set('limit', String(params.limit ?? 50));
  if (params.query) sp.set('query', params.query);
  const response = await apiFetch(`/api/v1/system/email-templates?${sp.toString()}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load email templates'));
  return response.json();
}

export async function getEmailTemplate(id: string): Promise<EmailTemplate> {
  const response = await apiFetch(`/api/v1/system/email-templates/${id}`);
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load email template'));
  return response.json();
}

export async function createEmailTemplate(body: EmailTemplateCreateBody): Promise<EmailTemplate> {
  const response = await apiFetch('/api/v1/system/email-templates', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to create email template'));
  return response.json();
}

export async function updateEmailTemplate(
  id: string,
  body: EmailTemplateUpdateBody,
): Promise<EmailTemplate> {
  const response = await apiFetch(`/api/v1/system/email-templates/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to update email template'));
  return response.json();
}

export async function deleteEmailTemplate(id: string): Promise<void> {
  const response = await apiFetch(`/api/v1/system/email-templates/${id}`, { method: 'DELETE' });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to delete email template'));
}

export async function previewEmailTemplate(
  id: string,
  context?: Record<string, unknown>,
): Promise<EmailTemplatePreview> {
  const response = await apiFetch(`/api/v1/system/email-templates/${id}/preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ context: context ?? null }),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to preview template'));
  return response.json();
}

export async function getTemplateVariableCatalog(): Promise<{ variables: TemplateVariable[] }> {
  const response = await apiFetch('/api/v1/system/email-templates/variables/catalog');
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load variable catalog'));
  return response.json();
}
