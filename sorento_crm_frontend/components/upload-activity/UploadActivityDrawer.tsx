'use client';

/**
 * Upload Activity drawer - right-side Sheet, opens via context state.
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
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { ScrollArea } from '@/components/ui/scroll-area';

import { Button } from '@/components/ui/button';

import { dismissKey, dismissSessions, pruneDismissed } from './dismissedSessions';
import { EmptyState } from './EmptyState';
import { UploadSessionRow } from './UploadSessionRow';
import { useUploadActivity } from './useUploadActivity';
import { useUploadManager } from './UploadManagerContext';

export function UploadActivityDrawer() {
  const { state, setDrawerOpen } = useUploadManager();
  const { sessions, badgeCount, refetch } = useUploadActivity();

  useEffect(() => {
    if (state.isDrawerOpen) refetch();
  }, [state.isDrawerOpen, refetch]);

  // Opening the drawer IS the dismissal: the badge counts sessions that want
  // attention, and the user has now given it. Only sessions that are
  // `needs_action` right now are marked — an upload still in flight is not, so
  // if it goes on to fail the badge comes back rather than being pre-silenced.
  // Pruning in the same pass keeps the stored list to what the feed still shows.
  useEffect(() => {
    if (!state.isDrawerOpen || sessions.length === 0) return;
    pruneDismissed(sessions.map((s) => s.session_id));
    dismissSessions(sessions.filter((s) => s.needs_action).map(dismissKey));
  }, [state.isDrawerOpen, sessions]);

  // The manual out. Auto-marking above only reaches `needs_action`, which cannot
  // help a session stuck on `processing` — an attachment with no
  // `integration_log` reads as "Linking…" for ever and pinned the badge with
  // nothing the user could do. This dismisses everything listed, whatever its
  // state; because the stored key carries the state, a session that later
  // changes starts counting again by itself.
  const dismissAll = () => dismissSessions(sessions.map(dismissKey));

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
          {/* Radix points the panel's `aria-describedby` at this node. Without it every
              open logs "Missing `Description` ... for {DialogContent}" and the panel
              reaches a screen reader as a title with no body. Screen-reader only: the
              header is one compact row, and on-screen prose is not wanted here. */}
          <SheetDescription className="sr-only">
            Recent uploads and imports, newest first.
          </SheetDescription>
          {badgeCount > 0 && (
            <Button
              variant="ghost"
              size="sm"
              className="ms-auto h-7 px-2 text-xs text-muted-foreground"
              onClick={dismissAll}
            >
              Dismiss all
            </Button>
          )}
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
