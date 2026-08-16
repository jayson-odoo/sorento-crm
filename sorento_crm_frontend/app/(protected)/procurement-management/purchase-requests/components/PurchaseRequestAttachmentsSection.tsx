'use client';

import { useMemo, useState } from 'react';
import { Download, ExternalLink, Link2, Paperclip, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { formatDate } from '@/lib/helpers';
import { useDeletePurchaseRequestAttachment } from '../hooks/usePurchaseRequests';
import { linkPurchaseRequestAttachment } from '../services/purchaseRequestService';
import type { PurchaseRequestAttachment } from '../types/purchaseRequest.types';
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

interface PurchaseRequestAttachmentsSectionProps {
  requestId: string;
  attachments?: PurchaseRequestAttachment[];
}

export default function PurchaseRequestAttachmentsSection({
  requestId,
  attachments: attachmentsFromRequest = [],
}: PurchaseRequestAttachmentsSectionProps) {
  const [linkDialogOpen, setLinkDialogOpen] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewIndex, setPreviewIndex] = useState(0);
  const [unlinkTarget, setUnlinkTarget] = useState<{ id: string; name: string } | null>(null);
  const deleteMutation = useDeletePurchaseRequestAttachment();

  const attachments = useMemo(
    () =>
      attachmentsFromRequest.filter(
        (link) => link.file_name != null || link.file_url != null,
      ),
    [attachmentsFromRequest],
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
        attachmentsFromRequest
          .map((a) => a.attachment_id)
          .filter((id): id is string => !!id),
      ),
    [attachmentsFromRequest],
  );

  const formatFileSize = (bytes: number | null | undefined) => {
    if (!bytes) return '-';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(2)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2">
          <Paperclip className="size-5" />
          Linked Attachments
        </CardTitle>
        <Button onClick={() => setLinkDialogOpen(true)}>
          <Link2 className="size-4" />
          Link Attachment
        </Button>
      </CardHeader>
      <CardContent>
        {attachments.length === 0 ? (
          <div className="text-sm text-muted-foreground">No linked attachments.</div>
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>File Name</TableHead>
                  <TableHead>Uploaded By</TableHead>
                  <TableHead>File Size</TableHead>
                  <TableHead>Linked At</TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {attachments.map((link, idx) => {
                  const displayName =
                    link.original_filename ?? link.file_name ?? 'Unnamed file';
                  const uploaderLabel = attachmentUploaderLabel(
                    link.uploaded_by_name,
                    link.uploaded_by_role,
                  );
                  return (
                    <TableRow key={link.id}>
                      <TableCell className="font-medium" title={displayName}>
                        <span className="truncate block max-w-[280px]" title={displayName}>
                          {displayName}
                        </span>
                      </TableCell>
                      <TableCell>
                        <span className="truncate block max-w-[200px] text-sm" title={uploaderLabel}>
                          {uploaderLabel}
                        </span>
                      </TableCell>
                      <TableCell>{formatFileSize(link.file_size_bytes)}</TableCell>
                      <TableCell>
                        {link.uploaded_at ? formatDate(new Date(link.uploaded_at)) : '-'}
                      </TableCell>
                      <TableCell>
                        <div className="flex gap-2">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => {
                              setPreviewIndex(idx);
                              setPreviewOpen(true);
                            }}
                          >
                            <ExternalLink className="size-4" />
                            View
                          </Button>
                          <Button variant="outline" size="sm" asChild>
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
                            onClick={() =>
                              setUnlinkTarget({ id: link.id, name: displayName })
                            }
                            disabled={deleteMutation.isPending}
                          >
                            <Trash2 className="size-4" />
                            Unlink
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
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
              <strong>{unlinkTarget?.name}</strong> and this purchase request. The
              file itself is not deleted. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => {
                if (unlinkTarget) deleteMutation.mutate(unlinkTarget.id);
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
          entityId={requestId}
          linkedAttachmentIds={linkedAttachmentIds}
          linkAttachment={linkPurchaseRequestAttachment}
          invalidateQueryKeys={[
            ['purchase-request', requestId],
            ['purchase-requests'],
          ]}
          successEntityLabel="request"
        />
      )}
    </Card>
  );
}
