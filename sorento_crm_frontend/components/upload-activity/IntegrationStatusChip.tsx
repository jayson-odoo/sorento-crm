'use client';

/**
 * IntegrationStatusChip — compact badge shown in AttachmentDetailModal
 * header. Reads from `useAttachmentIntegrationLog` for the run status and
 * (optionally) the attachment object for the most up-to-date linked count.
 */

import { CheckCircle2, Info, Loader2, XCircle } from 'lucide-react';

import { Badge } from '@/components/ui/badge';

import { useAttachmentIntegrationLog } from './useAttachmentIntegrationLog';

interface AttachmentLikeForCount {
  linked_products?: { id: string }[] | null;
  linked_promotions?: { id: string }[] | null;
  linked_form?: { id: string } | null;
  linked_packing_lists?: { id: string }[] | null;
}

interface Props {
  attachmentId: string;
  attachment?: AttachmentLikeForCount | null;
}

function countLinked(a: AttachmentLikeForCount | null | undefined): number {
  if (!a) return 0;
  return (
    (a.linked_products?.length ?? 0) +
    (a.linked_promotions?.length ?? 0) +
    (a.linked_form ? 1 : 0) +
    (a.linked_packing_lists?.length ?? 0)
  );
}

export function IntegrationStatusChip({ attachmentId, attachment }: Props) {
  const { log } = useAttachmentIntegrationLog(attachmentId);
  const linkedCount = countLinked(attachment);

  // Attachment ground-truth wins: even if the log is processing/missing, show
  // Linked when the row actually has links.
  if (linkedCount > 0) {
    return (
      <Badge variant="success" size="sm">
        <CheckCircle2 className="size-3" />
        Linked · {linkedCount}
      </Badge>
    );
  }

  if (!log) return null;

  switch (log.status) {
    case 'linked':
      return (
        <Badge variant="success" size="sm">
          <CheckCircle2 className="size-3" />
          Linked
        </Badge>
      );
    case 'unlinked':
      return (
        <Badge variant="info" size="sm">
          <Info className="size-3" />
          No match
        </Badge>
      );
    case 'processing':
      return (
        <Badge variant="secondary" size="sm">
          <Loader2 className="size-3 animate-spin" />
          Processing
        </Badge>
      );
    case 'uploading':
      return (
        <Badge variant="secondary" size="sm">
          <Loader2 className="size-3 animate-spin" />
          Uploading
        </Badge>
      );
    case 'failed':
    case 'post_failed':
      return (
        <Badge variant="destructive" size="sm">
          <XCircle className="size-3" />
          Failed
        </Badge>
      );
    default:
      return null;
  }
}
