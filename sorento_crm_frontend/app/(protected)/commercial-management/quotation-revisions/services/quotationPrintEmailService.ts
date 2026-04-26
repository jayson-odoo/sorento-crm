import { apiFetch } from '@/lib/api';

const CM = '/api/commercial-management';

export type QuotationEmailPreview = {
  default_to: string;
  subject: string;
  body_html: string;
  pdf_attachment_filename: string;
  token_keys: string[];
};

export type QuotationEmailTemplateRow = {
  id: string;
  code: string;
  name: string;
  subject_template: string;
  body_html_template: string;
  is_active: boolean;
  is_default: boolean;
  sort_order: number;
};

function parseFilenameFromDisposition(header: string | null): string | null {
  if (!header) return null;
  const star = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (star?.[1]) {
    try {
      return decodeURIComponent(star[1].replace(/(^"|"$)/g, '').trim());
    } catch {
      return star[1].replace(/(^"|"$)/g, '').trim();
    }
  }
  const plain = /filename="([^"]+)"/i.exec(header) || /filename=([^;]+)/i.exec(header);
  if (plain?.[1]) return plain[1].trim().replace(/^"|"$/g, '');
  return null;
}

async function fetchQuotationPdf(revisionId: string): Promise<{ blob: Blob; filename: string }> {
  const res = await apiFetch(`${CM}/quotation-revisions/${revisionId}/print-pdf`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  });
  if (!res.ok) {
    const err = (await res.json().catch(() => ({}))) as {
      message?: string;
      detail?: unknown;
    };
    const raw = err.detail;
    const nested =
      raw && typeof raw === 'object' && raw !== null && 'message' in (raw as object)
        ? String((raw as { message?: string }).message)
        : null;
    const msg =
      (typeof err.message === 'string' && err.message.trim() ? err.message : null) ||
      (typeof raw === 'string' ? raw : null) ||
      nested ||
      'Failed to generate PDF';
    throw new Error(msg);
  }
  const blob = await res.blob();
  const fn =
    parseFilenameFromDisposition(res.headers.get('Content-Disposition')) ||
    `quotation-${revisionId.slice(0, 8)}.pdf`;
  return { blob, filename: fn };
}

export async function downloadQuotationPdf(revisionId: string): Promise<void> {
  const { blob, filename } = await fetchQuotationPdf(revisionId);
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

/** Opens the quotation PDF in a new tab (browser PDF viewer) without downloading. */
export async function openQuotationPdfPreview(revisionId: string): Promise<void> {
  const { blob } = await fetchQuotationPdf(revisionId);
  const url = URL.createObjectURL(blob);
  const win = window.open(url, '_blank', 'noopener,noreferrer');
  if (!win) {
    URL.revokeObjectURL(url);
    throw new Error('Popup blocked. Allow popups for this site to preview the PDF.');
  }
  win.focus?.();
  window.setTimeout(() => URL.revokeObjectURL(url), 120_000);
}

export async function previewQuotationEmail(
  revisionId: string,
  templateId?: string | null,
): Promise<QuotationEmailPreview> {
  const res = await apiFetch(`${CM}/quotation-revisions/${revisionId}/email-preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ template_id: templateId ?? null }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const msg = (err as { detail?: unknown })?.detail;
    throw new Error(typeof msg === 'string' ? msg : 'Preview failed');
  }
  return res.json() as Promise<QuotationEmailPreview>;
}

export async function sendQuotationEmail(payload: {
  revisionId: string;
  to: string[];
  cc: string[];
  bcc: string[];
  subject: string;
  body_html: string;
}): Promise<void> {
  const res = await apiFetch(`${CM}/quotation-revisions/${payload.revisionId}/send-email`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      to: payload.to,
      cc: payload.cc,
      bcc: payload.bcc,
      subject: payload.subject,
      body_html: payload.body_html,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const raw = (err as { detail?: unknown })?.detail;
    const msg =
      typeof raw === 'string'
        ? raw
        : raw && typeof raw === 'object' && 'message' in (raw as object)
          ? String((raw as { message?: string }).message)
          : 'Send failed';
    throw new Error(msg);
  }
}

export async function listQuotationEmailTemplates(): Promise<QuotationEmailTemplateRow[]> {
  const res = await apiFetch(`${CM}/quotation-email-templates?active_only=true`, { method: 'GET' });
  if (!res.ok) throw new Error('Failed to load templates');
  const data = await res.json();
  return (data?.data ?? []) as QuotationEmailTemplateRow[];
}

export async function listQuotationEmailTemplatesAll(): Promise<QuotationEmailTemplateRow[]> {
  const res = await apiFetch(`${CM}/quotation-email-templates?active_only=false`, { method: 'GET' });
  if (!res.ok) throw new Error('Failed to load templates');
  const data = await res.json();
  return (data?.data ?? []) as QuotationEmailTemplateRow[];
}

export async function createQuotationEmailTemplate(payload: {
  code: string;
  name: string;
  subject_template: string;
  body_html_template: string;
  is_active?: boolean;
  is_default?: boolean;
  sort_order?: number;
}): Promise<QuotationEmailTemplateRow> {
  const res = await apiFetch(`${CM}/quotation-email-templates`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error('Create failed');
  return res.json() as Promise<QuotationEmailTemplateRow>;
}

export async function patchQuotationEmailTemplate(
  id: string,
  payload: Partial<{
    code: string;
    name: string;
    subject_template: string;
    body_html_template: string;
    is_active: boolean;
    is_default: boolean;
    sort_order: number;
  }>,
): Promise<QuotationEmailTemplateRow> {
  const res = await apiFetch(`${CM}/quotation-email-templates/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error('Update failed');
  return res.json() as Promise<QuotationEmailTemplateRow>;
}

export async function deleteQuotationEmailTemplate(id: string): Promise<void> {
  const res = await apiFetch(`${CM}/quotation-email-templates/${id}`, { method: 'DELETE' });
  if (!res.ok) throw new Error('Delete failed');
}
