import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

/**
 * Cover letter and terms templates, matching `app/api/v1/projects/quotation_templates.py`
 * (mounted under `/config`):
 *
 *   GET  /config/quotation-templates?kind=terms        -> ListEnvelope<QuotationTemplate>
 *   POST /config/quotation-templates                   -> QuotationTemplate (201)
 *   PUT  /config/quotation-templates/{id}              -> QuotationTemplate (name, body_html)
 *   POST /config/quotation-templates/{id}/activate     -> QuotationTemplate
 */
const BASE = '/api/v1/project-sales/config/quotation-templates';

export type QuotationTemplateKind = 'cover_letter' | 'terms';

export interface QuotationTemplate {
  id: string;
  kind: QuotationTemplateKind;
  name: string;
  body_html: string;
  payment_terms?: string | null;
  validity?: string | null;
  is_active: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface QuotationTemplateBody {
  name: string;
  body_html: string;
  payment_terms?: string | null;
  validity?: string | null;
}

export async function listQuotationTemplates(
  kind: QuotationTemplateKind,
): Promise<QuotationTemplate[]> {
  const response = await apiFetch(`${BASE}?kind=${kind}`);
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load the quotation templates'));
  const body: { data: QuotationTemplate[] } = await response.json();
  return body.data;
}

export async function createQuotationTemplate(
  kind: QuotationTemplateKind,
  body: QuotationTemplateBody,
): Promise<QuotationTemplate> {
  const response = await apiFetch(BASE, {
    method: 'POST',
    body: JSON.stringify({ ...body, kind }),
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to create the template'));
  return response.json();
}

export async function updateQuotationTemplate(
  id: string,
  body: Partial<QuotationTemplateBody>,
): Promise<QuotationTemplate> {
  const response = await apiFetch(`${BASE}/${id}`, {
    method: 'PUT',
    body: JSON.stringify(body),
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to save the template'));
  return response.json();
}

export async function activateQuotationTemplate(id: string): Promise<QuotationTemplate> {
  const response = await apiFetch(`${BASE}/${id}/activate`, { method: 'POST' });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to activate the template'));
  return response.json();
}
