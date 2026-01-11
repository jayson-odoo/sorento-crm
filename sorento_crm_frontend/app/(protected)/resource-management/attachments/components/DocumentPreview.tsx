'use client';

import type { Attachment } from '../types/attachment.types';

interface DocumentPreviewProps {
  attachment: Attachment;
}

export default function DocumentPreview({ attachment }: DocumentPreviewProps) {
  // TODO: Implement document preview or fallback
  return (
    <div className="text-center py-8">
      <p className="text-sm text-muted-foreground">Preview not available for this format</p>
      <p className="text-xs text-muted-foreground mt-2">Open in Microsoft Office Online</p>
    </div>
  );
}
