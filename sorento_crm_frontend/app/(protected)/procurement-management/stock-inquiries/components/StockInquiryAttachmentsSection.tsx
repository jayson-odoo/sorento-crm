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
import {
  useDeleteStockInquiryAttachment,
} from '../hooks/useStockInquiries';
import { linkStockInquiryAttachment } from '../services/stockInquiryService';
import type { StockInquiryAttachment } from '../types/stockInquiry.types';
import ComplaintLinkAttachmentBrowserDialog from '@/app/(protected)/complaint-management/complaints/components/ComplaintLinkAttachmentBrowserDialog';

interface StockInquiryAttachmentsSectionProps {
  inquiryId: string;
  attachments?: StockInquiryAttachment[];
}

export default function StockInquiryAttachmentsSection({
  inquiryId,
  attachments: attachmentsFromInquiry = [],
}: StockInquiryAttachmentsSectionProps) {
  const [linkDialogOpen, setLinkDialogOpen] = useState(false);
  const deleteMutation = useDeleteStockInquiryAttachment();

  const attachments = useMemo(
    () =>
      attachmentsFromInquiry.filter(
        (link) => link.file_name != null || link.file_url != null,
      ),
    [attachmentsFromInquiry],
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
                  <TableHead>File Size</TableHead>
                  <TableHead>Linked At</TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {attachments.map((link) => {
                  const displayName =
                    link.original_filename ?? link.file_name ?? 'Unnamed file';
                  const previewUrl =
                    link.file_url?.startsWith('http') === true
                      ? link.file_url
                      : link.attachment_id
                        ? `/api/v1/resource-management/attachments/${link.attachment_id}/download`
                        : link.file_url ?? '#';
                  return (
                    <TableRow key={link.id}>
                      <TableCell className="font-medium" title={displayName}>
                        <span className="truncate block max-w-[280px]" title={displayName}>
                          {displayName}
                        </span>
                      </TableCell>
                      <TableCell>{formatFileSize(link.file_size_bytes)}</TableCell>
                      <TableCell>
                        {link.uploaded_at ? formatDate(new Date(link.uploaded_at)) : '-'}
                      </TableCell>
                      <TableCell>
                        <div className="flex gap-2">
                          <Button variant="outline" size="sm" asChild>
                            <a
                              href={previewUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                            >
                              <ExternalLink className="size-4" />
                              View
                            </a>
                          </Button>
                          <Button variant="outline" size="sm" asChild>
                            <a
                              href={
                                link.attachment_id
                                  ? `/api/v1/resource-management/attachments/${link.attachment_id}/download`
                                  : previewUrl
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
                            onClick={() => deleteMutation.mutate(link.id)}
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
      {linkDialogOpen && (
        <ComplaintLinkAttachmentBrowserDialog
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
    </Card>
  );
}

