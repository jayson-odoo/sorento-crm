'use client';

/**
 * My Downloads drawer — right-side Sheet, opens via context state.
 *
 * Single instance mounted near the top nav. On open: force `refetch()` to honour
 * the "no stale data" invariant. Each row shows status; ready rows expose a
 * Download button that resolves a fresh signed URL on click and opens it.
 */

import { useEffect, useState } from 'react';
import { Download, FileText, Loader2, AlertCircle, CheckCircle2 } from 'lucide-react';
import { toast } from 'sonner';

import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Button } from '@/components/ui/button';
import { formatDateTimeInMalaysia } from '@/lib/helpers';

import { fetchDownloadUrl, type MyDownload } from '@/services/myDownloadsService';
import { useMyDownloads } from './MyDownloadsContext';

const KIND_LABEL: Record<string, string> = {
  complaint_pdf: 'Complaint PDF',
};

function StatusBadge({ status }: { status: MyDownload['status'] }) {
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

function DownloadRow({ row }: { row: MyDownload }) {
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

  return (
    <div className="flex items-start gap-3 border-b border-border px-4 py-3">
      <FileText className="mt-0.5 size-5 shrink-0 text-muted-foreground" />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium" title={row.filename ?? undefined}>
          {row.filename ?? KIND_LABEL[row.kind] ?? row.kind}
        </p>
        <p className="text-xs text-muted-foreground">
          {KIND_LABEL[row.kind] ?? row.kind}
          {row.created_at ? ` · ${formatDateTimeInMalaysia(new Date(row.created_at))}` : ''}
        </p>
        <div className="mt-1 flex items-center gap-3">
          <StatusBadge status={row.status} />
          {row.status === 'failed' && row.error && (
            <span className="truncate text-xs text-destructive" title={row.error}>
              {row.error}
            </span>
          )}
        </div>
      </div>
      {row.status === 'ready' && (
        <Button size="sm" variant="outline" disabled={busy} onClick={onDownload}>
          <Download className="size-4 mr-1" />
          {busy ? '…' : 'Download'}
        </Button>
      )}
    </div>
  );
}

export function MyDownloadsDrawer() {
  const { isOpen, setOpen, downloads, isLoading, refetch } = useMyDownloads();

  useEffect(() => {
    if (isOpen) refetch();
  }, [isOpen, refetch]);

  return (
    <Sheet open={isOpen} onOpenChange={setOpen}>
      <SheetContent
        side="right"
        className="p-0 gap-0 sm:w-[460px] sm:max-w-none inset-5 start-auto h-auto rounded-lg [&_[data-slot=sheet-close]]:top-4.5 [&_[data-slot=sheet-close]]:end-5"
      >
        <SheetHeader className="mb-0 flex flex-row items-center gap-2 space-y-0 px-4 py-3 pe-12 text-start border-b border-border">
          <SheetTitle className="p-0 text-base leading-none">My downloads</SheetTitle>
        </SheetHeader>
        <SheetBody className="p-0">
          <ScrollArea className="h-[calc(100vh-12rem)] min-h-[200px]">
            {downloads.length === 0 ? (
              <div className="flex flex-col items-center justify-center gap-2 px-4 py-16 text-center">
                <Download className="size-8 text-muted-foreground/50" />
                <p className="text-sm font-medium">No downloads yet</p>
                <p className="text-xs text-muted-foreground">
                  {isLoading
                    ? 'Loading…'
                    : 'Exports you generate (e.g. complaint PDFs) will appear here.'}
                </p>
              </div>
            ) : (
              <div>
                {downloads.map((row) => (
                  <DownloadRow key={row.id} row={row} />
                ))}
              </div>
            )}
          </ScrollArea>
        </SheetBody>
      </SheetContent>
    </Sheet>
  );
}
