'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Download, RefreshCw, Trash2 } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { Badge, BadgeDot } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDate } from '@/lib/helpers';
import RecordNavigation from '@/components/common/RecordNavigation';
import {
  useAttachments,
  useDeleteAttachment,
  useDownloadAttachment,
  useResubmitAttachmentWebhook,
  useRestoreAttachment,
} from '../hooks/useAttachments';
import { getAttachmentMetadata } from '../services/attachmentService';
import type { Attachment } from '../types/attachment.types';
import AttachmentDeleteDialog from './attachment-delete-dialog';

interface AttachmentDetailProps {
  attachmentId: string;
}

export default function AttachmentDetail({ attachmentId }: AttachmentDetailProps) {
  const router = useRouter();
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const deleteMutation = useDeleteAttachment();
  const downloadMutation = useDownloadAttachment();
  const resubmitMutation = useResubmitAttachmentWebhook();
  const restoreMutation = useRestoreAttachment();

  const { data: attachment, isLoading } = useQuery({
    queryKey: ['attachment-metadata', attachmentId],
    queryFn: () => getAttachmentMetadata(attachmentId),
    enabled: !!attachmentId,
    retry: 1,
  });

  const navigationParams = useMemo(
    () => ({
      pageIndex: 0,
      pageSize: 100,
      sorting: [{ id: 'uploaded_at', desc: true }],
      searchQuery: '',
    }),
    [],
  );
  const { data: navigationData } = useAttachments(navigationParams);
  const navigationItems = navigationData?.data ?? [];

  const formatFileSize = (bytes: number | null | undefined) => {
    if (!bytes) return '-';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(2)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  const handleDownload = async (file: Attachment) => {
    try {
      const blob = await downloadMutation.mutateAsync(file.id);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = file.original_filename || 'download';
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch {
      // handled by toast in mutation
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  if (!attachment) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">Attachment not found</p>
        <Button
          variant="outline"
          onClick={() => router.push('/resource-management/attachments')}
          className="mt-4"
        >
          Back to Attachments
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="space-y-1">
          <h1 className="text-2xl font-bold">{attachment.original_filename}</h1>
          <p className="text-sm text-muted-foreground">
            Uploaded: {formatDate(new Date(attachment.uploaded_at))}
          </p>
        </div>
        <div className="flex gap-2">
          <RecordNavigation
            currentId={attachmentId}
            items={navigationItems}
            basePath="/resource-management/attachments"
          />
          <Button
            variant="outline"
            onClick={() => handleDownload(attachment)}
            disabled={downloadMutation.isPending}
          >
            <Download className="size-4" />
            Download
          </Button>
          <Button
            variant="outline"
            onClick={() => resubmitMutation.mutate(attachment.id)}
            disabled={resubmitMutation.isPending || attachment.is_deleted}
          >
            <RefreshCw className={`size-4 ${resubmitMutation.isPending ? 'animate-spin' : ''}`} />
            Resubmit
          </Button>
          {attachment.is_deleted ? (
            <Button
              variant="outline"
              onClick={() => restoreMutation.mutate(attachment.id)}
              disabled={restoreMutation.isPending}
            >
              Restore
            </Button>
          ) : (
            <Button variant="destructive" onClick={() => setDeleteDialogOpen(true)}>
              <Trash2 className="size-4" />
              Delete
            </Button>
          )}
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Attachment Details</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <p className="text-sm text-muted-foreground">File Type</p>
              <p className="font-medium">{attachment.mime_type || '-'}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">File Size</p>
              <p className="font-medium">{formatFileSize(attachment.file_size_bytes)}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Entity Type</p>
              <p className="font-medium">{attachment.entity_type || '-'}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Entity ID</p>
              <p className="font-medium">{attachment.entity_id || '-'}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Uploaded By</p>
              <p className="font-medium">
                {attachment.uploaded_by_user?.name || attachment.uploaded_by || '-'}
              </p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Status</p>
              <Badge
                variant={attachment.is_deleted ? 'destructive' : 'success'}
                appearance="ghost"
              >
                <BadgeDot />
                {attachment.is_deleted ? 'Deleted' : 'Active'}
              </Badge>
            </div>
            {attachment.file_hash && (
              <div className="md:col-span-2">
                <p className="text-sm text-muted-foreground">File Hash</p>
                <p className="font-medium font-mono break-all">{attachment.file_hash}</p>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      <AttachmentDeleteDialog
        open={deleteDialogOpen}
        onOpenChange={setDeleteDialogOpen}
        attachment={attachment}
      />
    </div>
  );
}
