'use client';

/**
 * Per-file leaf row inside an expanded session.
 *
 * Click → opens AttachmentDetailModal for that attachment (Phase 1
 * placeholder: navigates to /resource-management/attachment-directories
 * with a hash so the panel highlights it; Phase 2 will route directly
 * once a stable detail-modal-by-id URL is exposed).
 */

import { useRouter } from 'next/navigation';
import {
  AlertCircle,
  CheckCircle2,
  Info,
  Loader2,
  RotateCw,
  XCircle,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

import { summariseFile } from './translation';
import type { UploadActivityFile } from './types';
import { useUploadManager } from './UploadManagerContext';

interface Props {
  sessionId: string;
  file: UploadActivityFile;
  /** Closes the drawer when navigating to detail. */
  onCloseDrawer?: () => void;
}

function StatusIcon({ status }: { status: UploadActivityFile['status'] }) {
  switch (status) {
    case 'linked':
      return <CheckCircle2 className="size-4 text-green-600 shrink-0" />;
    case 'uploading':
    case 'processing':
      return <Loader2 className="size-4 text-muted-foreground animate-spin shrink-0" />;
    case 'unlinked':
      return <Info className="size-4 text-blue-500 shrink-0" />;
    case 'failed':
      return <XCircle className="size-4 text-destructive shrink-0" />;
    case 'post_failed':
      return <AlertCircle className="size-4 text-destructive shrink-0" />;
    default:
      return <Info className="size-4 text-muted-foreground shrink-0" />;
  }
}

export function UploadFileRow({ sessionId, file, onCloseDrawer }: Props) {
  const router = useRouter();
  const { retryFile } = useUploadManager();

  const canOpenDetail = file.attachment_id != null;
  const canRetry = file.status === 'post_failed';

  const handleOpen = () => {
    if (!canOpenDetail) return;
    onCloseDrawer?.();
    // Files page reads `?attachment_id=<id>` and opens the detail modal +
    // strips the param. See AttachmentsInFolderPanel's deep-link effect.
    router.push(
      `/resource-management/attachment-directories?attachment_id=${file.attachment_id}`,
    );
  };

  return (
    <div
      className={cn(
        'flex items-start gap-2 px-4 py-2 text-sm border-l-2 border-transparent',
        canOpenDetail && 'hover:bg-muted/50 cursor-pointer',
        file.status === 'failed' || file.status === 'post_failed'
          ? 'border-l-destructive/30'
          : file.status === 'unlinked'
            ? 'border-l-blue-300'
            : '',
      )}
      onClick={canOpenDetail ? handleOpen : undefined}
    >
      <StatusIcon status={file.status} />
      <div className="flex-1 min-w-0">
        <div className="truncate font-medium" title={file.filename}>
          {file.filename}
        </div>
        <div className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
          {summariseFile(file)}
        </div>
      </div>
      {canRetry && (
        <Button
          variant="outline"
          size="sm"
          className="h-7 px-2 text-xs shrink-0"
          onClick={(e) => {
            e.stopPropagation();
            void retryFile(sessionId, file.client_id);
          }}
        >
          <RotateCw className="size-3 me-1" />
          Retry
        </Button>
      )}
    </div>
  );
}
