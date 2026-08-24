'use client';

/**
 * My Downloads drawer - right-side Sheet, opens via context state.
 *
 * Single instance mounted near the top nav. On open: force `refetch()` to honour
 * the "no stale data" invariant. Each row shows status; ready rows expose a
 * Download button that resolves a fresh signed URL on click and opens it.
 */

import { useEffect } from 'react';
import { Download } from 'lucide-react';

import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { ScrollArea } from '@/components/ui/scroll-area';

import { DownloadRow } from './DownloadRow';
import { useMyDownloads } from './MyDownloadsContext';

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
