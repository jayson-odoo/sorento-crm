'use client';

/**
 * Shared rendering for a single "My Downloads" row + status badge.
 *
 * Used by both the top-nav drawer (MyDownloadsDrawer) and the per-entity
 * downloads modal (EntityDownloadsModal) so date pills, status, and the
 * click-to-download behaviour can't drift between the two surfaces.
 *
 * The whole row is clickable when the download is ready: clicking resolves a
 * fresh signed URL and opens it in a new tab. Non-ready rows are inert.
 */

import { useState } from 'react';
import { Download, FileText, Loader2, AlertCircle, CheckCircle2 } from 'lucide-react';
import { toast } from 'sonner';

import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { fetchDownloadUrl, type MyDownload } from '@/services/myDownloadsService';

export const KIND_LABEL: Record<string, string> = {
  complaint_pdf: 'Complaint PDF',
  // Named after the document itself - the form is headed PRODUCT INQUIRY FORM -
  // while the entity key stays stock_inquiry.
  stock_inquiry_pdf: 'Product Inquiry PDF',
  chat_history_export: 'Chat History CSV',
  promotions_pdf: 'Promotions PDF',
};

export function StatusBadge({ status }: { status: MyDownload['status'] }) {
  if (status === 'ready') {
    return (
      <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-700">
        <CheckCircle2 className="size-3.5" /> Ready
      </span>
    );
  }
  if (status === 'failed') {
    return (
      <span className="inline-flex items-center gap-1 text-xs font-medium text-destructive">
        <AlertCircle className="size-3.5" /> Failed
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-xs font-medium text-muted-foreground">
      <Loader2 className="size-3.5 animate-spin" />
      {status === 'pending' ? 'Queued' : 'Preparing'}
    </span>
  );
}

export function DownloadRow({ row }: { row: MyDownload }) {
  const [busy, setBusy] = useState(false);

  const onDownload = async () => {
    setBusy(true);
    try {
      const { url } = await fetchDownloadUrl(row.id);
      window.open(url, '_blank', 'noopener,noreferrer');
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not open download');
    } finally {
      setBusy(false);
    }
  };

  const ready = row.status === 'ready';

  return (
    <div
      role={ready ? 'button' : undefined}
      tabIndex={ready ? 0 : undefined}
      onClick={ready && !busy ? onDownload : undefined}
      onKeyDown={
        ready && !busy
          ? (e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onDownload();
              }
            }
          : undefined
      }
      title={ready ? 'Click to download' : undefined}
      aria-busy={busy || undefined}
      className={`flex items-start gap-3 border-b border-border px-4 py-3 ${
        ready ? 'cursor-pointer transition-colors hover:bg-muted/50' : ''
      } ${busy ? 'opacity-60' : ''}`}
    >
      <FileText className="mt-0.5 size-5 shrink-0 text-muted-foreground" />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium" title={row.filename ?? undefined}>
          {row.filename ?? KIND_LABEL[row.kind] ?? row.kind}
        </p>
        <p className="text-xs text-muted-foreground">
          {KIND_LABEL[row.kind] ?? row.kind}
          {row.created_at ? ` · ${formatDateTimeInMalaysia(new Date(row.created_at))}` : ''}
        </p>
        <div className="mt-1 flex min-w-0 items-center gap-3">
          <StatusBadge status={row.status} />
          {row.status === 'failed' && row.error && (
            <span className="min-w-0 truncate text-xs text-destructive" title={row.error}>
              {row.error}
            </span>
          )}
        </div>
      </div>
      {ready && (
        <Download
          className={`mt-0.5 size-4 shrink-0 text-muted-foreground ${busy ? 'animate-pulse' : ''}`}
        />
      )}
    </div>
  );
}
