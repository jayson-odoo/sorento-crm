'use client';

/**
 * IntegrationCard - Card-wrapped variant of IntegrationPanel.
 *
 * Currently unused inside AttachmentDetailModal (the modal embeds
 * IntegrationPanel into a tab instead). Kept here as an exported
 * primitive in case other surfaces want the full-card view.
 *
 * Reads the latest integration_log via the same Phase-2 hook as
 * IntegrationPanel.
 */

import {
  CheckCircle2,
  Info,
  Loader2,
  XCircle,
} from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

import { IntegrationPanel } from './IntegrationPanel';
import { useAttachmentIntegrationLog } from './useAttachmentIntegrationLog';
import type { UploadActivityFile } from './types';

interface Props {
  attachmentId: string;
}

function HeaderBadge({ status }: { status: UploadActivityFile['status'] }) {
  switch (status) {
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
          Unlinked
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
    default:
      return null;
  }
}

export function IntegrationCard({ attachmentId }: Props) {
  const { log } = useAttachmentIntegrationLog(attachmentId);

  return (
    <Card>
      <CardHeader className="py-4 flex flex-row items-center gap-2 space-y-0">
        <CardTitle className="text-base">Integration</CardTitle>
        {log && (
          <div className="ms-auto">
            <HeaderBadge status={log.status} />
          </div>
        )}
      </CardHeader>
      <CardContent className="pt-0">
        <IntegrationPanel attachmentId={attachmentId} />
      </CardContent>
    </Card>
  );
}
