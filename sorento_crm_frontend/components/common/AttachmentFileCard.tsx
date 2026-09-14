'use client';

import { Download, Eye, Unlink } from 'lucide-react';
import { toast } from '@/lib/toast';
import { Button } from '@/components/ui/button';
import { useDownloadAttachment } from '@/app/(protected)/resource-management/attachments/hooks/useAttachments';
import { getAttachmentPreviewUrl } from '@/app/(protected)/resource-management/attachments/services/attachmentService';

/**
 * One uploaded file, as a row a person can read and act on.
 *
 * The packing list's Related Documents card had the only copy: name, `type - size`, an eye,
 * a download and an unlink. The proforma invoice's Source files section listed its own files
 * as plain text with no way to open them, and building a second version of the same row is
 * how the two drift into two answers to "what does a file look like here". Unlink is the one
 * optional half, because only a link can be undone; a file that simply IS the record's source
 * has nothing to detach.
 */

/** What the second line reads: the type, and the size when we hold one.
 *
 *  A file whose size was never recorded says the type alone rather than "Type - -": the
 *  dash answers nothing, and a row that states a fact it does not have reads as a defect.
 */
function metaLabel(
  typeLabel: string | null | undefined,
  bytes: number | null | undefined,
): string {
  const type = typeLabel || 'No type';
  if (bytes == null) return type;
  return `${type} • ${(bytes / 1024).toFixed(2)} KB`;
}

export interface AttachmentFileCardProps {
  /** The attachment this row opens and downloads. */
  attachmentId: string;
  /** The file's own name, as it was uploaded. */
  name: string;
  /** The attachment type in words ("Packing list"), not its id. */
  typeLabel?: string | null;
  sizeBytes?: number | null;
  /** Given, the row offers Unlink; omitted, it does not. */
  onUnlink?: () => void;
  /** While the caller's unlink is in flight. */
  unlinkDisabled?: boolean;
}

export function AttachmentFileCard({
  attachmentId,
  name,
  typeLabel,
  sizeBytes,
  onUnlink,
  unlinkDisabled,
}: AttachmentFileCardProps) {
  const downloadMutation = useDownloadAttachment();

  const handlePreview = async () => {
    try {
      const previewUrl = await getAttachmentPreviewUrl(attachmentId);
      // `noopener,noreferrer`: the URL is a signed link off a storage provider, and a tab
      // opened without them keeps a handle on this one through `window.opener`.
      if (previewUrl) window.open(previewUrl, '_blank', 'noopener,noreferrer');
    } catch {
      toast.error('Failed to open attachment preview');
    }
  };

  const handleDownload = async () => {
    try {
      const blob = await downloadMutation.mutateAsync(attachmentId);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = name || 'download';
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch {
      // The mutation hook has already said what went wrong.
    }
  };

  return (
    <div className="flex items-center gap-2 rounded-lg border p-3" data-testid="attachment-file">
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium" title={name}>
          {name}
        </p>
        <p className="text-xs text-muted-foreground">{metaLabel(typeLabel, sizeBytes)}</p>
      </div>
      <div className="flex shrink-0 gap-2">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => void handlePreview()}
          aria-label={`Preview ${name}`}
          title="Preview"
        >
          <Eye className="size-4" />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => void handleDownload()}
          aria-label={`Download ${name}`}
          title="Download"
        >
          <Download className="size-4" />
        </Button>
        {onUnlink ? (
          <Button
            variant="ghost"
            size="sm"
            onClick={onUnlink}
            disabled={unlinkDisabled}
            aria-label={`Unlink ${name}`}
            title="Unlink attachment"
          >
            <Unlink className="size-4" />
          </Button>
        ) : null}
      </div>
    </div>
  );
}

export default AttachmentFileCard;
