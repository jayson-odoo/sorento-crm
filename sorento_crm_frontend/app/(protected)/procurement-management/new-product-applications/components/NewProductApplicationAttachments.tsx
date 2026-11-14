'use client';

/**
 * The attachments of a saved new product application: the shared `EntityAttachmentsSection`
 * with the application's link route and its deferred unlink. `editable` is the owner of a Draft
 * or Rejected application; everyone else only reads the list.
 */

import { EntityAttachmentsSection } from '@/components/common/EntityAttachmentsSection';
import type { NewProductApplicationAttachment } from '@/types/newProductApplication';
import { linkNewProductApplicationAttachment } from '../services/newProductApplicationService';

export default function NewProductApplicationAttachments({
  applicationId,
  attachments,
  editable,
}: {
  applicationId: string;
  attachments: NewProductApplicationAttachment[];
  editable: boolean;
}) {
  return (
    <EntityAttachmentsSection<NewProductApplicationAttachment>
      entityId={applicationId}
      attachments={attachments}
      editable={editable}
      linkAttachment={linkNewProductApplicationAttachment}
      unlinkActionKey="new_product_application_attachment.unlink"
      unlinkEntityType="new_product_application_attachment"
      invalidateKeys={[['new-product-application', applicationId], ['new-product-applications']]}
      entityLabel="application"
    />
  );
}
