'use client';

/**
 * Upload Activity drawer — right-side Sheet, opens via context state.
 *
 * Single instance mounted near the top nav. Icon → dispatches
 * `setDrawerOpen(true)` to open. On open: force `refetch()` to honour
 * the "no stale data" invariant from `feedback_drawer_no_stale_data`
 * memory. Phase 1 refetch is a no-op; Phase 2 hits BE.
 */

import { useEffect } from 'react';

import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { ScrollArea } from '@/components/ui/scroll-area';

import { EmptyState } from './EmptyState';
import { UploadSessionRow } from './UploadSessionRow';
import { useUploadActivity } from './useUploadActivity';
import { useUploadManager } from './UploadManagerContext';

export function UploadActivityDrawer() {
  const { state, setDrawerOpen } = useUploadManager();
  const { sessions, refetch } = useUploadActivity();

  useEffect(() => {
    if (state.isDrawerOpen) refetch();
  }, [state.isDrawerOpen, refetch]);

  return (
    <Sheet open={state.isDrawerOpen} onOpenChange={(o) => setDrawerOpen(o)}>
      <SheetContent
        side="right"
        className="p-0 gap-0 sm:w-[500px] sm:max-w-none inset-5 start-auto h-auto rounded-lg [&_[data-slot=sheet-close]]:top-4.5 [&_[data-slot=sheet-close]]:end-5"
      >
        <SheetHeader className="mb-0 flex flex-row items-center gap-2 space-y-0 px-4 py-3 pe-12 text-start border-b border-border">
          <SheetTitle className="p-0 text-base leading-none">
            Upload activity
          </SheetTitle>
        </SheetHeader>
        <SheetBody className="p-0">
          <ScrollArea className="h-[calc(100vh-12rem)] min-h-[200px]">
            {sessions.length === 0 ? (
              <EmptyState />
            ) : (
              <div>
                {sessions.map((s, i) => (
                  <UploadSessionRow
                    key={s.session_id}
                    session={s}
                    defaultExpanded={i === 0 && s.needs_action}
                    onCloseDrawer={() => setDrawerOpen(false)}
                  />
                ))}
              </div>
            )}
          </ScrollArea>
        </SheetBody>
      </SheetContent>
    </Sheet>
  );
}
