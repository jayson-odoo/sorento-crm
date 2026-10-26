'use client';

import { useMemo, useState } from 'react';
import { Download, Eye } from 'lucide-react';
import { Button } from '@/components/ui/button';
import AttachmentPreviewModal, {
  type AttachmentPreviewItem,
} from '@/components/common/AttachmentPreviewModal';
import { saveBlobAs } from '@/lib/save-blob';
import { toast } from '@/lib/toast';
import {
  downloadEmailOutboxAttachment,
  emailOutboxAttachmentUrl,
} from '../services/emailOutboxService';
import type { EmailOutboxAttachment } from '../types/emailOutbox.types';

/** The kinds the shared preview modal draws from bytes read through an authenticated route.
 *  An image needs a public url there, which this route is not, so images are Download only. */
const PREVIEWABLE = /\.(xlsx?|xlsm|csv|pdf)$/i;

/**
 * Every file the outbox row's email carries, so the person checking the email can open the
 * exact file that was (or will be) sent. Files are addressed by their position in the row's
 * own list; the server serves nothing else.
 */
export default function EmailOutboxAttachments({
  rowId,
  attachments,
}: {
  rowId: string;
  attachments: EmailOutboxAttachment[];
}) {
  const [downloading, setDownloading] = useState<number | null>(null);
  const [previewIndex, setPreviewIndex] = useState<number | null>(null);

  const previewItems = useMemo<AttachmentPreviewItem[]>(
    () =>
      attachments
        .filter((a) => PREVIEWABLE.test(a.filename))
        .map((a) => ({
          id: `${rowId}:${a.index}`,
          name: a.filename,
          url: '',
          downloadUrl: emailOutboxAttachmentUrl(rowId, a.index),
        })),
    [attachments, rowId],
  );

  if (attachments.length === 0) return null;

  async function download(a: EmailOutboxAttachment) {
    setDownloading(a.index);
    try {
      saveBlobAs(await downloadEmailOutboxAttachment(rowId, a.index), a.filename);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to download attachment');
    } finally {
      setDownloading(null);
    }
  }

  return (
    <div>
      <div className="text-muted-foreground text-sm mb-1">Attachments</div>
      <ul className="rounded border divide-y">
        {attachments.map((a) => (
          <li key={a.index} className="flex flex-wrap items-center gap-2 px-3 py-2 text-sm">
            {/* Own line on a phone, so the whole name (the OI number) stays readable. */}
            <span className="min-w-0 basis-full truncate sm:basis-0 sm:flex-1" title={a.filename}>
              {a.filename}
            </span>
            {PREVIEWABLE.test(a.filename) && (
              <Button
                variant="outline"
                size="sm"
                aria-label={`Preview ${a.filename}`}
                onClick={() =>
                  setPreviewIndex(previewItems.findIndex((i) => i.id === `${rowId}:${a.index}`))
                }
              >
                <Eye className="size-4" />
                Preview
              </Button>
            )}
            <Button
              variant="outline"
              size="sm"
              aria-label={`Download ${a.filename}`}
              disabled={downloading === a.index}
              onClick={() => void download(a)}
            >
              <Download className="size-4" />
              Download
            </Button>
          </li>
        ))}
      </ul>
      <AttachmentPreviewModal
        open={previewIndex !== null}
        onOpenChange={(open) => !open && setPreviewIndex(null)}
        items={previewItems}
        startIndex={previewIndex ?? 0}
      />
    </div>
  );
}
