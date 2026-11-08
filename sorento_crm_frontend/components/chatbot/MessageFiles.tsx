'use client';

import { FileSpreadsheet, FileText } from 'lucide-react';
import type { SentFile } from '@/lib/aiAssistantChatApi';

function detail(file: SentFile): string | null {
  if (file.kind === 'sheet') {
    const rows = file.rows_total ?? file.rows_read;
    const label = file.sheet || 'Sheet';
    return rows != null ? `${label}, ${rows} rows` : label;
  }
  if (file.kind === 'pdf' && file.pages != null) return `${file.pages} pages`;
  return null;
}

/** The files a user sent, right-aligned above their bubble. */
export function MessageFiles({ files }: { files: SentFile[] }) {
  if (!files.length) return null;
  return (
    <div className="flex flex-wrap justify-end gap-1.5">
      {files.map((file) => {
        const link = file.url || undefined;
        const linkProps = link
          ? { href: link, target: '_blank', rel: 'noopener noreferrer' }
          : {};
        if (file.kind === 'image' && file.thumb_url) {
          return (
            <a
              key={file.id}
              {...linkProps}
              title={file.filename}
              className="block size-16 overflow-hidden rounded-lg border border-border bg-background"
            >
              <img src={file.thumb_url} alt={file.filename} className="size-full object-cover" />
            </a>
          );
        }
        const Icon = file.kind === 'sheet' ? FileSpreadsheet : FileText;
        const sub = detail(file);
        return (
          <a
            key={file.id}
            {...linkProps}
            title={file.filename}
            className="flex max-w-full items-center gap-2 rounded-lg border border-border bg-background px-2 py-1.5 text-xs"
          >
            <Icon className="size-4 shrink-0 text-muted-foreground" aria-hidden />
            <span className="flex min-w-0 flex-col">
              <span className="max-w-[150px] truncate font-medium">{file.filename}</span>
              {sub ? <span className="text-2xs text-muted-foreground">{sub}</span> : null}
            </span>
          </a>
        );
      })}
    </div>
  );
}

export default MessageFiles;
