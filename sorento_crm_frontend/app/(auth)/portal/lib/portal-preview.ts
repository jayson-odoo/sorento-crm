/**
 * Portal wiring for the shared AttachmentPreviewModal.
 *
 * The portal previews in place - it never opens an attachment in a new tab -
 * and it has no NextAuth session, so the modal's default `apiFetch` byte
 * reader would 401. Both surfaces that preview portal attachments (the
 * dropzone list and the staff-reply carousel on the submission form) build
 * their items and their byte reader from here, so the two cannot drift.
 */
import type { AttachmentPreviewItem } from '@/components/common/AttachmentPreviewModal';
import {
  fetchPortalAttachmentBytes,
  portalAttachmentDownloadUrl,
  type PortalAttachment,
} from './portal-client';

/** Uploaded attachment -> preview item. `id` stays the link id (the row
 *  identity in the list); the bytes route is keyed on the attachment id. */
export function toPreviewItem(a: PortalAttachment): AttachmentPreviewItem {
  return {
    id: a.link_id,
    name: a.filename || 'Attachment',
    url: a.url ?? '',
    downloadUrl: a.attachment_id
      ? portalAttachmentDownloadUrl(a.attachment_id)
      : undefined,
    sizeBytes: a.size,
  };
}

export { canPreviewLocally } from '@/components/common/ai-extract/canPreviewLocally';

/** `fetchBytes` for AttachmentPreviewModal on the portal (token auth). */
export function portalFetchBytes(item: AttachmentPreviewItem): Promise<Response> {
  if (!item.downloadUrl) {
    return Promise.reject(new Error('This attachment has no download route.'));
  }
  return fetchPortalAttachmentBytes(item.downloadUrl);
}
