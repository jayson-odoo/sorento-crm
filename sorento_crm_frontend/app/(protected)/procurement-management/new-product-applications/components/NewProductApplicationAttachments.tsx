'use client';

/**
 * The attachments of a saved new product application: Stock Inquiry's flow (a list of files and
 * "Link Attachment" through the shared library browser) with one difference the app has retired
 * the confirm dialog for: Unlink is a server-deferred row action with a countdown and a Cancel.
 * `editable` is the owner of a Draft or Rejected application; everyone else only reads the list.
 */

import { useMemo, useState } from 'react';
import { Link2, Paperclip, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import LinkAttachmentBrowserDialog from '@/components/common/LinkAttachmentBrowserDialog';
import { useDeferredRowAction } from '@/hooks/useDeferredRowAction';
import { formatDate } from '@/lib/helpers';
import type { NewProductApplicationAttachment } from '@/types/newProductApplication';
import { linkNewProductApplicationAttachment } from '../services/newProductApplicationService';

const sizeLabel = (bytes: number | null | undefined) => {
  if (!bytes) return '-';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(2)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
};

export default function NewProductApplicationAttachments({
  applicationId,
  attachments,
  editable,
}: {
  applicationId: string;
  attachments: NewProductApplicationAttachment[];
  editable: boolean;
}) {
  const [linkOpen, setLinkOpen] = useState(false);
  const unlink = useDeferredRowAction({
    actionKey: 'new_product_application_attachment.unlink',
    entityType: 'new_product_application_attachment',
    verb: 'Unlinking',
    successMessage: 'Attachment unlinked',
    invalidateKeys: [
      ['new-product-application', applicationId],
      ['new-product-applications'],
    ],
  });

  const linkedIds = useMemo(
    () => new Set(attachments.map((a) => a.attachment_id)),
    [attachments],
  );

  return (
    <>
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 className="flex items-center gap-2 text-base font-semibold">
          <Paperclip className="size-5" />
          Linked Attachments
        </h3>
        {editable && (
          <Button type="button" onClick={() => setLinkOpen(true)}>
            <Link2 className="size-4" />
            Link Attachment
          </Button>
        )}
      </div>
      {attachments.length === 0 ? (
        <div className="rounded-lg border border-dashed px-6 py-8 text-center text-sm font-medium">
          No linked attachments.
        </div>
      ) : (
        <div className="relative overflow-x-auto rounded-lg border">
          <table className="w-full min-w-[560px] table-fixed text-sm">
            <thead className="bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="px-3 py-2 text-left font-medium">File Name</th>
                <th className="w-28 px-3 py-2 text-left font-medium">
                  File Size
                </th>
                <th className="w-36 px-3 py-2 text-left font-medium">
                  Linked At
                </th>
                {editable && (
                  <th className="w-32 px-3 py-2">
                    <span className="sr-only">Actions</span>
                  </th>
                )}
              </tr>
            </thead>
            <tbody>
              {attachments.map((a) => {
                const name = a.filename ?? 'Unnamed file';
                return (
                  <tr key={a.link_id} className="border-t">
                    <td className="px-3 py-2">
                      {a.url ? (
                        <a
                          href={a.url}
                          target="_blank"
                          rel="noreferrer"
                          className="block truncate font-medium text-primary hover:underline"
                          title={name}
                        >
                          {name}
                        </a>
                      ) : (
                        <span
                          className="block truncate font-medium"
                          title={name}
                        >
                          {name}
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2">{sizeLabel(a.size)}</td>
                    <td className="px-3 py-2">
                      {a.uploaded_at
                        ? formatDate(new Date(a.uploaded_at))
                        : '-'}
                    </td>
                    {editable && (
                      <td className="px-3 py-2">
                        <Button
                          type="button"
                          variant="destructive"
                          size="sm"
                          aria-label={`Unlink ${name}`}
                          disabled={unlink.targetId === a.link_id}
                          onClick={() =>
                            unlink.run({ id: a.link_id, subject: name })
                          }
                        >
                          <Trash2 className="size-4" />
                          Unlink
                        </Button>
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {unlink.countdown}
      {linkOpen && (
        <LinkAttachmentBrowserDialog
          open={linkOpen}
          onOpenChange={setLinkOpen}
          entityId={applicationId}
          linkedAttachmentIds={linkedIds}
          linkAttachment={linkNewProductApplicationAttachment}
          invalidateQueryKeys={[
            ['new-product-application', applicationId],
            ['new-product-applications'],
          ]}
          successEntityLabel="application"
        />
      )}
    </>
  );
}
