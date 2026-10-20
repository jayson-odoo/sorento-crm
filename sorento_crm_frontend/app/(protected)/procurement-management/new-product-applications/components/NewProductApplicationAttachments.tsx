'use client';

/**
 * The attachments of a saved new product application: Stock Inquiry's flow (the shared PanelDataGrid of files and
 * "Link Attachment" through the shared library browser) with one difference the app has retired
 * the confirm dialog for: Unlink is a server-deferred row action with a countdown and a Cancel.
 * `editable` is the owner of a Draft or Rejected application; everyone else only reads the list.
 */

import { useMemo, useState } from 'react';
import type { ColumnDef } from '@tanstack/react-table';
import { Link2, Paperclip, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import LinkAttachmentBrowserDialog from '@/components/common/LinkAttachmentBrowserDialog';
import { PanelDataGrid } from '@/components/common/PanelDataGrid';
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

  const columns = useMemo<ColumnDef<NewProductApplicationAttachment>[]>(() => {
    const cols: ColumnDef<NewProductApplicationAttachment>[] = [
      {
        id: 'file_name',
        accessorFn: (row) => row.filename ?? 'Unnamed file',
        header: ({ column }) => (
          <DataGridColumnHeader title="File Name" column={column} />
        ),
        cell: ({ row }) => {
          const name = row.original.filename ?? 'Unnamed file';
          return row.original.url ? (
            <a
              href={row.original.url}
              target="_blank"
              rel="noreferrer"
              className="block max-w-[280px] truncate font-medium text-primary hover:underline"
              title={name}
            >
              {name}
            </a>
          ) : (
            <span
              className="block max-w-[280px] truncate font-medium"
              title={name}
            >
              {name}
            </span>
          );
        },
        size: 260,
        meta: { headerTitle: 'File Name' },
      },
      {
        id: 'file_size',
        accessorFn: (row) => row.size ?? 0,
        header: ({ column }) => (
          <DataGridColumnHeader title="File Size" column={column} />
        ),
        cell: ({ row }) => sizeLabel(row.original.size),
        size: 110,
        meta: { headerTitle: 'File Size' },
      },
      {
        id: 'uploaded_at',
        accessorFn: (row) => row.uploaded_at ?? '',
        header: ({ column }) => (
          <DataGridColumnHeader title="Linked At" column={column} />
        ),
        cell: ({ row }) =>
          row.original.uploaded_at
            ? formatDate(new Date(row.original.uploaded_at))
            : '-',
        size: 140,
        meta: { headerTitle: 'Linked At' },
      },
    ];
    if (editable) {
      cols.push({
        id: 'actions',
        header: () => <span className="sr-only">Actions</span>,
        cell: ({ row }) => {
          const name = row.original.filename ?? 'Unnamed file';
          return (
            <Button
              type="button"
              variant="destructive"
              size="sm"
              aria-label={`Unlink ${name}`}
              disabled={unlink.targetId === row.original.link_id}
              onClick={() =>
                unlink.run({ id: row.original.link_id, subject: name })
              }
            >
              <Trash2 className="size-4" />
              Unlink
            </Button>
          );
        },
        size: 130,
        enableResizing: false,
        meta: { headerTitle: 'Actions' },
      });
    }
    return cols;
  }, [editable, unlink]);

  return (
    <>
      <PanelDataGrid<NewProductApplicationAttachment>
        title={
          <span className="flex items-center gap-2">
            <Paperclip className="size-5" />
            Linked Attachments
          </span>
        }
        toolbar={
          editable ? (
            <Button type="button" onClick={() => setLinkOpen(true)}>
              <Link2 className="size-4" />
              Link Attachment
            </Button>
          ) : undefined
        }
        columns={columns}
        rows={attachments}
        getRowId={(row) => row.link_id}
        listingKey={null}
        emptyTitle="No linked attachments."
      />
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
