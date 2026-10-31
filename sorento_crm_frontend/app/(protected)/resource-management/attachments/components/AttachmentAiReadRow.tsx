'use client';

import { Button } from '@/components/ui/button';
import { useReadAttachmentAgain } from '../hooks/useReadAttachmentAgain';
import type { Attachment } from '../types/attachment.types';

const AI_READ_LABELS: Record<string, string> = {
  queued: 'Queued',
  processing: 'Processing',
  done: 'Done',
  failed: 'Failed',
  unsupported: 'Not supported',
};

/** Statuses that are still moving: the detail query refetches while the status is one of these. */
export function isAiReadInFlight(status: string | null | undefined): boolean {
  return status === 'queued' || status === 'processing';
}

function aiReadSummary(a: Attachment): string {
  const parts = [AI_READ_LABELS[a.ai_read_status ?? ''] ?? String(a.ai_read_status)];
  if (a.ai_read_status === 'done') {
    if (a.ai_read_pages != null) parts.push(`${a.ai_read_pages} ${a.ai_read_pages === 1 ? 'page' : 'pages'}`);
    const ocr = a.ai_read_ocr_pages ?? 0;
    if (ocr > 0) {
      const cost = Number(a.ai_read_cost_usd ?? 0);
      parts.push(`${ocr} read by OCR (est. USD ${cost.toFixed(cost > 0 && cost < 0.01 ? 3 : 2)})`);
    }
  }
  return parts.join(', ');
}

/** The "Read by AI" row of an attachment: status, pages, OCR pages, est. cost, error, Read again. */
export default function AttachmentAiReadRow({ attachment }: { attachment: Attachment }) {
  const readAgainMutation = useReadAttachmentAgain();
  if (!attachment.ai_read_status) return null;
  return (
    <div className="min-w-0">
      <p className="text-sm text-muted-foreground">Read by AI</p>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-medium">{aiReadSummary(attachment)}</p>
        {(attachment.ai_read_status === 'done' || attachment.ai_read_status === 'failed') && (
          <Button
            variant="ghost"
            size="sm"
            disabled={readAgainMutation.isPending}
            onClick={() => readAgainMutation.mutate(attachment.id)}
          >
            Read again
          </Button>
        )}
      </div>
      {attachment.ai_read_status === 'failed' && attachment.ai_read_error && (
        <p className="text-sm text-destructive break-words">{attachment.ai_read_error}</p>
      )}
    </div>
  );
}
