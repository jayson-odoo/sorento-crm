import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type { CoverDesign, CoverPageData } from '@/lib/quotation-cover';

/**
 * Cover letter and terms templates, matching `app/api/v1/projects/quotation_templates.py`
 * (mounted under `/config`):
 *
 *   GET  /config/quotation-templates?kind=terms        -> ListEnvelope<QuotationTemplate>
 *   POST /config/quotation-templates                   -> QuotationTemplate (201)
 *   PUT  /config/quotation-templates/{id}              -> QuotationTemplate (name, body_html)
 *   POST /config/quotation-templates/{id}/activate     -> QuotationTemplate
 *   GET  /config/quotation-templates/merge-fields      -> ListEnvelope<MergeField>
 *   POST /config/quotation-templates/cover-preview     -> CoverPageData (an unsaved design, stores nothing)
 *
 * kind `cover_page` is a cover page design: the intro is `body_html`, the rest is `design`.
 */
const BASE = '/api/v1/project-sales/config/quotation-templates';

export type QuotationTemplateKind = 'cover_letter' | 'terms' | 'cover_page';

export interface QuotationTemplate {
  id: string;
  kind: QuotationTemplateKind;
  name: string;
  body_html: string;
  payment_terms?: string | null;
  validity?: string | null;
  /** kind cover_page only. */
  design?: CoverDesign | null;
  is_active: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface QuotationTemplateBody {
  name: string;
  body_html: string;
  payment_terms?: string | null;
  validity?: string | null;
  design?: CoverDesign;
}

/** One merge field the intro and closing text may use. */
export interface MergeField {
  token: string;
  placeholder: string;
  label: string;
  example: string;
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

export async function listMergeFields(): Promise<MergeField[]> {
  const response = await apiFetch(`${BASE}/merge-fields`);
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load the merge fields'));
  const body: { data: MergeField[] } = await response.json();
  return body.data;
}

export async function previewCoverDesign(body: {
  design: CoverDesign;
  body_html: string;
}): Promise<CoverPageData> {
  const response = await apiFetch(`${BASE}/cover-preview`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to preview the cover page'));
  return response.json();
}
