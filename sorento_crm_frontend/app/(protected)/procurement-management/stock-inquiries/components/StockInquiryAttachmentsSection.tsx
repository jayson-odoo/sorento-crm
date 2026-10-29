'use client';

import { useMemo, useState } from 'react';
import type { ColumnDef } from '@tanstack/react-table';
import { Download, ExternalLink, Link2, Paperclip, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { PanelDataGrid } from '@/components/common/PanelDataGrid';
import { formatDate } from '@/lib/helpers';
import {
  useDeleteStockInquiryAttachment,
  useDeleteStockInquiryResponseAttachment,
} from '../hooks/useStockInquiries';
import { linkStockInquiryAttachment } from '../services/stockInquiryService';
import type { StockInquiryAttachment } from '../types/stockInquiry.types';
import LinkAttachmentBrowserDialog from '@/components/common/LinkAttachmentBrowserDialog';
import { attachmentUploaderLabel } from '@/app/(protected)/master-data-management/shared/lib/attachment-attribution';
import AttachmentPreviewModal, {
  type AttachmentPreviewItem,
} from '@/components/common/AttachmentPreviewModal';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';

interface StockInquiryAttachmentsSectionProps {
  inquiryId: string;
  attachments?: StockInquiryAttachment[];
}

export default function StockInquiryAttachmentsSection({
  inquiryId,
  attachments: attachmentsFromInquiry = [],
}: StockInquiryAttachmentsSectionProps) {
  const [linkDialogOpen, setLinkDialogOpen] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewIndex, setPreviewIndex] = useState(0);
  const [unlinkTarget, setUnlinkTarget] = useState<{
    id: string;
    name: string;
    isResponseAttachment: boolean;
  } | null>(null);
  const deleteMutation = useDeleteStockInquiryAttachment();
  const deleteResponseAttachmentMutation = useDeleteStockInquiryResponseAttachment();
  const unlinkPending = deleteMutation.isPending || deleteResponseAttachmentMutation.isPending;

  const attachments = useMemo(
    () =>
      attachmentsFromInquiry.filter(
        (link) => link.file_name != null || link.file_url != null,
      ),
    [attachmentsFromInquiry],
  );

  const previewItems = useMemo<AttachmentPreviewItem[]>(
    () =>
      attachments.map((link) => {
        const name = link.original_filename ?? link.file_name ?? 'Unnamed file';
        const cdn = link.file_url?.startsWith('http') ? link.file_url : undefined;
        const download = link.attachment_id
          ? `/api/v1/resource-management/attachments/${link.attachment_id}/download`
          : undefined;
        return {
          id: link.id,
          name,
          url: cdn ?? '',
          downloadUrl: download ?? cdn,
          sizeBytes: link.file_size_bytes,
        };
      }),
    [attachments],
  );

  const linkedAttachmentIds = useMemo(
    () =>
      new Set(
        attachmentsFromInquiry
          .map((a) => a.attachment_id)
          .filter((id): id is string => !!id),
      ),
    [attachmentsFromInquiry],
  );

  const formatFileSize = (bytes: number | null | undefined) => {
    if (!bytes) return '-';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(2)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  const columns = useMemo<ColumnDef<StockInquiryAttachment>[]>(
    () => [
      {
        id: 'file_name',
        accessorFn: (row) => row.original_filename ?? row.file_name ?? 'Unnamed file',
        header: ({ column }) => <DataGridColumnHeader title="File Name" column={column} />,
        cell: ({ row }) => {
          const displayName =
            row.original.original_filename ?? row.original.file_name ?? 'Unnamed file';
          return (
            <span className="truncate block max-w-[280px] font-medium" title={displayName}>
              {displayName}
            </span>
          );
        },
        size: 260,
        meta: { headerTitle: 'File Name' },
      },
      {
        id: 'uploaded_by',
        accessorFn: (row) =>
          attachmentUploaderLabel(row.uploaded_by_name, row.uploaded_by_role),
        header: ({ column }) => <DataGridColumnHeader title="Uploaded By" column={column} />,
        cell: ({ row }) => {
          const uploaderLabel = attachmentUploaderLabel(
            row.original.uploaded_by_name,
            row.original.uploaded_by_role,
          );
          return (
            <span className="truncate block max-w-[200px] text-sm" title={uploaderLabel}>
              {uploaderLabel}
            </span>
          );
        },
        size: 180,
        meta: { headerTitle: 'Uploaded By' },
      },
      {
        id: 'file_size_bytes',
        accessorFn: (row) => row.file_size_bytes ?? 0,
        header: ({ column }) => <DataGridColumnHeader title="File Size" column={column} />,
        cell: ({ row }) => formatFileSize(row.original.file_size_bytes),
        size: 110,
        meta: { headerTitle: 'File Size' },
      },
      {
        id: 'uploaded_at',
        accessorFn: (row) => row.uploaded_at ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Linked At" column={column} />,
        cell: ({ row }) =>
          row.original.uploaded_at ? formatDate(new Date(row.original.uploaded_at)) : '-',
        size: 140,
        meta: { headerTitle: 'Linked At' },
      },
      {
        id: 'actions',
        header: () => <span className="sr-only">Actions</span>,
        cell: ({ row }) => {
          const link = row.original;
          const displayName = link.original_filename ?? link.file_name ?? 'Unnamed file';
          const isResponseAttachment = link.link_type === 'response_attachment';
          return (
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={(e) => {
                  e.stopPropagation();
                  setPreviewIndex(attachments.indexOf(link));
                  setPreviewOpen(true);
                }}
              >
                <ExternalLink className="size-4" />
                View
              </Button>
              <Button variant="outline" size="sm" asChild onClick={(e) => e.stopPropagation()}>
                <a
                  href={
                    link.attachment_id
                      ? `/api/v1/resource-management/attachments/${link.attachment_id}/download`
                      : (link.file_url ?? '#')
                  }
                  download={displayName}
                >
                  <Download className="size-4" />
                  Download
                </a>
              </Button>
              <Button
                variant="destructive"
                size="sm"
                onClick={(e) => {
                  e.stopPropagation();
                  setUnlinkTarget({ id: link.id, name: displayName, isResponseAttachment });
                }}
                disabled={unlinkPending}
              >
                <Trash2 className="size-4" />
                Unlink
              </Button>
            </div>
          );
        },
        size: 320,
        enableResizing: false,
        meta: { headerTitle: 'Actions' },
      },
    ],
    [attachments, unlinkPending],
  );

  return (
    <>
      <PanelDataGrid<StockInquiryAttachment>
        title={
          <span className="flex items-center gap-2">
            <Paperclip className="size-5" />
            Linked Attachments
          </span>
        }
        toolbar={
          <Button onClick={() => setLinkDialogOpen(true)}>
            <Link2 className="size-4" />
            Link Attachment
          </Button>
        }
        columns={columns}
        rows={attachments}
        getRowId={(row) => row.id}
        listingKey="procurement.stock_inquiries.view::manual-attachments"
        emptyTitle="No linked attachments."
      />
      <AttachmentPreviewModal
        open={previewOpen}
        onOpenChange={setPreviewOpen}
        items={previewItems}
        startIndex={previewIndex}
      />
      <AlertDialog
        open={!!unlinkTarget}
        onOpenChange={(o) => {
          if (!o) setUnlinkTarget(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Unlink attachment?</AlertDialogTitle>
            <AlertDialogDescription>
              This removes the link between{' '}
              <strong>{unlinkTarget?.name}</strong> and this stock inquiry. The
              file itself is not deleted. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => {
                if (unlinkTarget) {
                  if (unlinkTarget.isResponseAttachment) {
                    deleteResponseAttachmentMutation.mutate(unlinkTarget.id);
                  } else {
                    deleteMutation.mutate(unlinkTarget.id);
                  }
                }
                setUnlinkTarget(null);
              }}
            >
              Unlink
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      {linkDialogOpen && (
        <LinkAttachmentBrowserDialog
          open={linkDialogOpen}
          onOpenChange={setLinkDialogOpen}
          entityId={inquiryId}
          linkedAttachmentIds={linkedAttachmentIds}
          linkAttachment={linkStockInquiryAttachment}
          invalidateQueryKeys={[
            ['stock-inquiry', inquiryId],
            ['stock-inquiries'],
          ]}
          successEntityLabel="stock inquiry"
        />
      )}
    </>
  );
}

