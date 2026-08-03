import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

/**
 * Project documents ride the SHARED resource-management attachment API.
 *
 * No project_attachments table and no project-specific upload route: the generic
 * `attachments` endpoint already takes `entity_type` + `entity_id` on the multipart form and
 * writes the `entity_attachment_links` row itself, and the list endpoint already filters on
 * the same pair. Building a parallel path would have given tender drawings a second home
 * that the Files screen, the trash, the storage migration and the preview modal all know
 * nothing about.
 *
 * The Documents tab therefore uploads and lists here, and the file it stores is the same row
 * Resource Management → Files shows.
 *
 * `attachment_type_id` is REQUIRED by that endpoint (it 400s without one, and the type decides
 * the storage prefix and whether a webhook fires), so the dialog asks for it rather than
 * inventing a project-only default.
 */
const BASE = '/api/resource-management/attachments';

/**
 * Field names taken from `AttachmentResponse`, not guessed: the size is `file_size_bytes`,
 * the uploader is a nested `uploaded_by_user.name`, and the type is a nested
 * `attachment_type.type_name`. The first pass assumed flat `file_size` / `uploaded_by_name` /
 * `attachment_type_name` and rendered three columns of "-" against a real row.
 */
export interface ProjectDocument {
  id: string;
  original_filename?: string | null;
  stored_filename?: string | null;
  file_size_bytes?: number | null;
  mime_type?: string | null;
  file_path?: string | null;
  uploaded_at?: string | null;
  uploaded_by_user?: { id: string; name?: string | null } | null;
  attachment_type?: { id: string; type_name: string } | null;
}

export async function listProjectDocuments(projectId: string): Promise<ProjectDocument[]> {
  const params = new URLSearchParams({
    entity_type: 'project',
    entity_id: projectId,
    limit: '200',
    sort: 'uploaded_at',
    dir: 'desc',
  });
  const response = await apiFetch(`${BASE}/?${params.toString()}`);
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not load this project’s documents'));
  }
  const body = await response.json();
  return body?.data ?? [];
}

export interface AttachmentTypeOption {
  id: string;
  type_name: string;
  code?: string | null;
}

/** The same vocabulary the Files screen offers, so a project document is filed like any other. */
export async function listAttachmentTypeOptions(): Promise<AttachmentTypeOption[]> {
  const response = await apiFetch(
    '/api/resource-management/attachment-types?limit=200&sort=type_name&dir=asc',
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not load the document types'));
  }
  const body = await response.json();
  return body?.data ?? [];
}

export async function uploadProjectDocument(
  projectId: string,
  file: File,
  attachmentTypeId: string,
): Promise<ProjectDocument> {
  const form = new FormData();
  form.append('file', file);
  form.append('entity_type', 'project');
  form.append('entity_id', projectId);
  form.append('attachment_type_id', attachmentTypeId);
  const response = await apiFetch(`${BASE}/`, { method: 'POST', body: form });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not upload this document'));
  }
  return response.json();
}

export async function deleteProjectDocument(attachmentId: string): Promise<void> {
  const response = await apiFetch(`${BASE}/${attachmentId}`, { method: 'DELETE' });
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Could not delete this document'));
  }
}
