/**
 * Byte route for the public /view pages (complaint, stock-inquiry).
 *
 * `file_url` on the summary is a signed storage URL (R2/S3/CloudFront) that sends no
 * CORS headers, so pdf.js cannot read it cross-origin - it lands in the viewer's error
 * state (PR #1256 review, blocking finding 1). This route is on our own backend, keyed
 * on the same view token the page itself reads with, so the browser can fetch it.
 *
 * There is no NextAuth session on these pages, so this bypasses `apiFetch` and, like the
 * portal's own attachment route (`app/(auth)/portal/lib/portal-client.ts`), goes to the
 * API host directly rather than through the Next.js `/api/v1/public/[...path]` catch-all,
 * which re-serializes every response as JSON and would hand back `{}` for PDF bytes.
 */
import type { AttachmentPreviewItem } from '@/components/common/AttachmentPreviewModal';

export type ViewEntity = 'complaint' | 'stock-inquiry';

function apiBase(): string {
  const env = typeof process !== 'undefined' ? process.env?.NEXT_PUBLIC_API_URL : undefined;
  return env ? env.replace(/\/$/, '') : '';
}

function absoluteApiUrl(path: string): string {
  const base = apiBase();
  if (base) return `${base}${path.startsWith('/') ? path : `/${path}`}`;
  if (typeof window !== 'undefined') {
    const port = window.location.port;
    if (port === '3000' || port === '3001') {
      return `${window.location.protocol}//${window.location.hostname}:8000${path}`;
    }
  }
  return path;
}

export function viewAttachmentDownloadUrl(
  entity: ViewEntity,
  attachmentId: string,
  token: string,
): string {
  return `/api/v1/public/view/${entity}/attachments/${encodeURIComponent(attachmentId)}/download?token=${encodeURIComponent(token)}`;
}

/** `fetchBytes` for AttachmentPreviewModal on a public /view page (view-token auth). */
export function fetchViewAttachmentBytes(item: AttachmentPreviewItem): Promise<Response> {
  if (!item.downloadUrl) {
    return Promise.reject(new Error('This attachment has no download route.'));
  }
  return fetch(absoluteApiUrl(item.downloadUrl));
}

/** Attachment shape common to the complaint and stock-inquiry view summaries. */
export interface ViewAttachmentLike {
  id?: string | null;
  attachment_id?: string | null;
  file_name?: string | null;
  original_filename?: string | null;
  file_url?: string | null;
}

/** One summary attachment -> a modal preview item, `downloadUrl` set whenever the
 *  attachment has an id to read bytes through (every row does; the fallback keeps
 *  a legacy row with none from crashing instead of previewing). */
export function toViewPreviewItem(
  att: ViewAttachmentLike,
  entity: ViewEntity,
  token: string,
  fallbackId: string,
): AttachmentPreviewItem {
  return {
    id: att.id ?? fallbackId,
    name: att.original_filename ?? att.file_name ?? 'Attachment',
    url: att.file_url ?? '',
    downloadUrl: att.attachment_id
      ? viewAttachmentDownloadUrl(entity, att.attachment_id, token)
      : undefined,
  };
}
