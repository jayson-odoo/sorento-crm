import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

/**
 * Clarification files on a core sales-order line (#1312,
 * PLAN-oi-line-attachments-27sep.md), shared by the fulfilment board's paperclip and
 * the order inquiry Lines tab.
 *
 * ── BACKEND CONTRACT (app/api/v1/projects/so_line_attachments.py) ──────────
 *  POST   /api/v1/project-sales/sales-order-lines/attachments/lookup   {line_ids}
 *         -> 200 { [line_id]: SoLineAttachment[] } (only lines that hold files)
 *  POST   /api/v1/project-sales/sales-order-lines/{lineId}/attachments   multipart files[]
 *         -> 200 SoLineAttachment[] (the line's full list, after the upload)
 *  DELETE goes through the deferred-action mechanism (D7), never a plain call from
 *         this file directly - `sales_order_line_attachment.delete`
 *         (`SoLineAttachmentsButton.tsx`'s `useDeferredRowAction`), same as every
 *         other list delete in this codebase. `deleteSoLineAttachment` below exists
 *         for parity with the other feature services in this domain, not for that x.
 *  Auth: `projects.projects.view` (lookup), `projects.projects.edit` (upload/delete).
 */

const BASE = '/api/v1/project-sales/sales-order-lines';

export interface SoLineAttachment {
  id: string;
  attachment_id: string;
  filename: string | null;
  size_bytes: number | null;
  content_type: string | null;
  url: string | null;
  thumbnail_url: string | null;
}

export type SoLineAttachmentsByLine = Record<string, SoLineAttachment[]>;

export async function lookupSoLineAttachments(
  lineIds: string[],
): Promise<SoLineAttachmentsByLine> {
  if (lineIds.length === 0) return {};
  const response = await apiFetch(`${BASE}/attachments/lookup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ line_ids: lineIds }),
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to load attachments'));
  return response.json();
}

export async function uploadSoLineAttachments(
  lineId: string,
  files: File[],
): Promise<SoLineAttachment[]> {
  const form = new FormData();
  for (const file of files) form.append('files', file);
  const response = await apiFetch(`${BASE}/${lineId}/attachments`, {
    method: 'POST',
    body: form,
  });
  if (!response.ok) throw new Error(await extractApiError(response, 'Failed to upload files'));
  return response.json();
}

export async function deleteSoLineAttachment(lineId: string, linkId: string): Promise<void> {
  const response = await apiFetch(`${BASE}/${lineId}/attachments/${linkId}`, {
    method: 'DELETE',
  });
  if (!response.ok)
    throw new Error(await extractApiError(response, 'Failed to delete that file'));
}
