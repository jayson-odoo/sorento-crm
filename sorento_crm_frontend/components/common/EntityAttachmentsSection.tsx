'use client';

/**
 * The attachments of a saved record (new product application, order change notice): Stock
 * Inquiry's flow (the shared PanelDataGrid of files and "Link Attachment" through the shared
 * library browser) with one difference the app has retired the confirm dialog for: Unlink is a
 * server-deferred row action with a countdown and a Cancel. `editable` is whoever may edit the
 * record while it is editable; everyone else only reads the list. Generic over the record type:
 * the caller names its link route, its unlink action and the queries to refresh.
 *
 * Owner rules: no action column and no row button; Unlink is in the row's right-click (long-press
 * on touch) menu, the PurchaseOrdersPanel pattern. "Link Attachment" is an outline button, so
 * the page keeps one filled main button. With `uploadFile`, a drop zone (drop, browse or paste)
 * uploads files straight onto the record; linking from the library stays as the second way.
 */

import { useMemo, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import type { ColumnDef } from '@tanstack/react-table';
import { Link2, Paperclip, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuTrigger,
} from '@/components/ui/context-menu';
import { ResponseAttachmentDropzone } from '@/app/(protected)/complaint-management/complaints/components/ResponseAttachmentDropzone';
import { toast } from '@/lib/toast';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import LinkAttachmentBrowserDialog from '@/components/common/LinkAttachmentBrowserDialog';
import { PanelDataGrid } from '@/components/common/PanelDataGrid';
import { useDeferredRowAction } from '@/hooks/useDeferredRowAction';
import { formatDateInMalaysia } from '@/lib/helpers';

/** One linked file, as `list_attachments_for_entity` answers it. */
export interface EntityAttachmentRow {
  link_id: string;
  attachment_id: string;
  filename: string | null;
  size: number | null;
  url: string | null;
  content_type?: string | null;
  uploaded_at?: string | null;
}

export interface EntityAttachmentsSectionProps<T extends EntityAttachmentRow> {
  entityId: string;
  attachments: T[];
  editable: boolean;
  /** POST the library file onto the record. */
  linkAttachment: (entityId: string, attachmentId: string) => Promise<unknown>;
  /** The record type's deferred unlink (`<type>_attachment.unlink`). */
  unlinkActionKey: string;
  unlinkEntityType: string;
  invalidateKeys: unknown[][];
  /** What the link toast calls the record ("application", "notice"). */
  entityLabel: string;
  /** Upload one file straight onto the record (the drop zone shows only when given). */
  uploadFile?: (entityId: string, file: File) => Promise<unknown>;
}

const sizeLabel = (bytes: number | null | undefined) => {
  if (!bytes) return '-';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(2)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
};

export function EntityAttachmentsSection<T extends EntityAttachmentRow>({
  entityId,
  attachments,
  editable,
  linkAttachment,
  unlinkActionKey,
  unlinkEntityType,
  invalidateKeys,
  entityLabel,
  uploadFile,
}: EntityAttachmentsSectionProps<T>) {
  const [linkOpen, setLinkOpen] = useState(false);
  const [menuRow, setMenuRow] = useState<T | null>(null);
  const [uploading, setUploading] = useState<File[]>([]);
  const queryClient = useQueryClient();

  /** Files go up as soon as they are dropped or chosen; each one says how it went. */
  const upload = async (files: File[]) => {
    if (!uploadFile) return;
    const fresh = files.filter((f) => !uploading.includes(f));
    setUploading(files);
    for (const file of fresh) {
      try {
        await uploadFile(entityId, file);
        toast.success(`${file.name} attached`);
      } catch (e) {
        toast.error(
          e instanceof Error ? e.message : `${file.name} could not be attached`,
        );
      }
    }
    setUploading([]);
    for (const key of invalidateKeys)
      void queryClient.invalidateQueries({ queryKey: key });
  };
  const unlink = useDeferredRowAction({
    actionKey: unlinkActionKey,
    entityType: unlinkEntityType,
    verb: 'Unlinking',
    successMessage: 'Attachment unlinked',
    invalidateKeys,
  });

  const linkedIds = useMemo(
    () => new Set(attachments.map((a) => a.attachment_id)),
    [attachments],
  );

  const columns = useMemo<ColumnDef<T>[]>(() => {
    const cols: ColumnDef<T>[] = [
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
            ? formatDateInMalaysia(row.original.uploaded_at)
            : '-',
        size: 140,
        meta: { headerTitle: 'Linked At' },
      },
    ];
    return cols;
  }, []);

  return (
    <>
      {editable && uploadFile && (
        <div className="mb-3">
          <ResponseAttachmentDropzone
            files={uploading}
            onFilesChange={(next) => void upload(next)}
            disabled={uploading.length > 0}
          />
        </div>
      )}
      <ContextMenu modal={false}>
        <ContextMenuTrigger asChild>
          <div
            // Capture phase: a right-click outside a file row (or on a read-only list) keeps the
            // browser's own menu instead of an empty one.
            onContextMenuCapture={(event) => {
              const rowEl = (event.target as Element).closest('[data-link-id]');
              const row = attachments.find(
                (a) => a.link_id === rowEl?.getAttribute('data-link-id'),
              );
              if (!row || !editable) {
                event.stopPropagation();
                return;
              }
              setMenuRow(row);
            }}
          >
            <PanelDataGrid<T>
              title={
                <span className="flex items-center gap-2">
                  <Paperclip className="size-5" />
                  Linked Attachments
                </span>
              }
              toolbar={
                editable ? (
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => setLinkOpen(true)}
                  >
                    <Link2 className="size-4" />
                    Link Attachment
                  </Button>
                ) : undefined
              }
              columns={columns}
              rows={attachments}
              getRowId={(row) => row.link_id}
              rowAttributes={(row) => ({ 'data-link-id': row.link_id })}
              listingKey={null}
              emptyTitle="No linked attachments."
            />
          </div>
        </ContextMenuTrigger>
        <ContextMenuContent className="w-48">
          {menuRow && (
            <ContextMenuItem
              variant="destructive"
              disabled={unlink.targetId === menuRow.link_id}
              onSelect={() =>
                unlink.run({
                  id: menuRow.link_id,
                  subject: menuRow.filename ?? 'Unnamed file',
                })
              }
            >
              <Trash2 className="size-4" />
              Unlink
            </ContextMenuItem>
          )}
        </ContextMenuContent>
      </ContextMenu>
      {unlink.countdown}
      {linkOpen && (
        <LinkAttachmentBrowserDialog
          open={linkOpen}
          onOpenChange={setLinkOpen}
          entityId={entityId}
          linkedAttachmentIds={linkedIds}
          linkAttachment={linkAttachment}
          invalidateQueryKeys={invalidateKeys}
          successEntityLabel={entityLabel}
        />
      )}
    </>
  );
}
