import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';
import type { TagSheetDesignPayload } from '@/lib/dealer-kit/design-payload';
import type { QueuedDownload } from './quotationDocumentService';

/**
 * Project spec sheet (PS-SPEC-SHEET): the Spec sheet tab of a quotation document.
 *
 *   GET  /projects/{projectId}/quotation-documents/{id}/spec-sheet[?issue_id=]  -> SpecSheetView
 *   PUT  /projects/{projectId}/quotation-documents/{id}/spec-sheet              -> SpecSheetView
 *   GET  /projects/{projectId}/quotation-documents/{id}/spec-sheet/preview[?issue_id=]
 *        -> the same payload the PDF prints from (cover + one sheet per visible page)
 *   POST /projects/{projectId}/quotation-documents/{id}/spec-sheet/export[?issue_id=]
 *        -> the queued download (My Downloads)
 */

const BASE = '/api/v1/project-sales';

export interface SpecSheetRow {
  key: string;
  area: string;
  comment: string;
  marker: string;
  hidden: boolean;
  accessories: string[];
}

export interface SpecSheetSettings {
  cover_template_id: string | null;
  page_template_id: string | null;
  single_page_template_id: string | null;
  issue_id: string | null;
  rows: SpecSheetRow[];
}

export interface SpecSheetAccessory {
  /** Set only on a hand-picked accessory: the item it came from. */
  key: string | null;
  source: 'set' | 'picked';
  product_id: string | null;
  code: string;
  name: string;
  brand: string;
}

export interface SpecSheetPage {
  key: string;
  line_id: string;
  product_id: string | null;
  code: string;
  name: string;
  brand: string;
  image_attachment_id: string | null;
  drawing_attachment_id: string | null;
  accessories: SpecSheetAccessory[];
  picked: string[];
  /** Typed on the page, else `area_default`. */
  area: string;
  /** The Section heading the line sits under on the Lines tab (owner, mock v5). */
  area_default: string;
  comment: string;
  marker: string;
  hidden: boolean;
}

export interface SpecSheetTemplateOption {
  id: string;
  name: string;
  width_mm: number | null;
  height_mm: number | null;
}

export interface SpecSheetIssueOption {
  id: string;
  issue_no: number;
  label: string;
  issued_at: string | null;
}

export interface SpecSheetView {
  settings: SpecSheetSettings;
  issue_id: string | null;
  issues: SpecSheetIssueOption[];
  pages: SpecSheetPage[];
  templates: { cover: SpecSheetTemplateOption[]; page: SpecSheetTemplateOption[] };
}

export type SpecSheetSettingsBody = Partial<SpecSheetSettings>;

/** What the preview answers: the print payload, plus the page size it was laid out at. */
export type SpecSheetPreview = Omit<TagSheetDesignPayload, 'page_id' | 'source'> & {
  page_size: { width_mm: number; height_mm: number };
};

function url(projectId: string, documentId: string, suffix = '', issueId?: string | null) {
  const query = issueId ? `?issue_id=${encodeURIComponent(issueId)}` : '';
  return `${BASE}/projects/${projectId}/quotation-documents/${documentId}/spec-sheet${suffix}${query}`;
}

export async function getSpecSheet(
  projectId: string,
  documentId: string,
  issueId?: string | null,
): Promise<SpecSheetView> {
  const response = await apiFetch(url(projectId, documentId, '', issueId));
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load the spec sheet'));
  return response.json();
}

export async function saveSpecSheet(
  projectId: string,
  documentId: string,
  body: SpecSheetSettingsBody,
): Promise<SpecSheetView> {
  const response = await apiFetch(url(projectId, documentId), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to save the spec sheet'));
  return response.json();
}

export async function getSpecSheetPreview(
  projectId: string,
  documentId: string,
  issueId?: string | null,
): Promise<SpecSheetPreview> {
  const response = await apiFetch(url(projectId, documentId, '/preview', issueId));
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to draw the spec sheet'));
  return response.json();
}

/** The open page's pictures at a sharper rendition than the strip's thumbnails. */
export async function getSpecSheetPageImages(
  projectId: string,
  documentId: string,
  issueId: string | null,
  key: string,
): Promise<{ images: Record<string, string> }> {
  const params = new URLSearchParams({ key });
  if (issueId) params.set('issue_id', issueId);
  const response = await apiFetch(
    `${url(projectId, documentId, '/page-images')}?${params.toString()}`,
  );
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load the page'));
  return response.json();
}

export async function queueSpecSheetPdf(
  projectId: string,
  documentId: string,
  issueId?: string | null,
): Promise<QueuedDownload> {
  const response = await apiFetch(url(projectId, documentId, '/export', issueId), {
    method: 'POST',
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to queue the spec sheet'));
  return response.json();
}
