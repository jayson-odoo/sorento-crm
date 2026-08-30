'use client';

import { ReactNode, useEffect, useMemo, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import {
  listNotifications,
  getUnreadCount,
  markRead,
  markUnread,
  markAllRead,
  archive,
  archiveAll,
  deleteNotification,
  deleteNotificationsBulk,
  deleteAllNotifications,
} from '@/services/notificationService';
import { toast } from 'sonner';
import NotificationItem from './notifications/NotificationItem';

const UNREAD_POLL_INTERVAL_MS = 10_000; // 10s so bell badge updates soon after job completion
const TITLE_UNREAD_PREFIX = /^\(\d+\)\s*/; // strip "(3) " from title to get base

function getBaseTitle(): string {
  if (typeof document === 'undefined') return 'Sorento';
  return document.title.replace(TITLE_UNREAD_PREFIX, '').trim() || 'Sorento';
}

export function NotificationsSheet({ trigger }: { trigger: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<'inbox' | 'archived'>('inbox');
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [confirmBulk, setConfirmBulk] = useState<'selected' | 'all' | null>(null);
  const queryClient = useQueryClient();

  const { data: unreadCount = 0, refetch: refetchUnread } = useQuery({
    queryKey: ['notifications', 'unread-count'],
    queryFn: () => getUnreadCount(false),
    refetchInterval: UNREAD_POLL_INTERVAL_MS,
  });

  // Tab title: always show (n) in browser tab when there are unread notifications
  useEffect(() => {
    if (typeof document === 'undefined') return;
    const base = getBaseTitle();
    document.title = unreadCount > 0 ? `(${unreadCount}) ${base}` : base;
  }, [unreadCount]);

  // When tab becomes visible again, re-apply title in case another tab or route changed it
  useEffect(() => {
    if (typeof document === 'undefined') return;
    const handleVisibility = () => {
      const base = getBaseTitle();
      document.title = unreadCount > 0 ? `(${unreadCount}) ${base}` : base;
    };
    document.addEventListener('visibilitychange', handleVisibility);
    return () => document.removeEventListener('visibilitychange', handleVisibility);
  }, [unreadCount]);

  const { data: listData, isLoading, refetch } = useQuery({
    queryKey: ['notifications', 'list', tab],
    queryFn: () => listNotifications({ tab, limit: 50 }),
    enabled: open,
  });

  useEffect(() => {
    setSelectedIds([]);
  }, [tab]);

  useEffect(() => {
    if (!open) setSelectedIds([]);
  }, [open]);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['notifications'] });
    refetchUnread();
  };

  const handleMarkRead = async (id: string) => {
    await markRead(id);
    invalidate();
  };
  const handleMarkUnread = async (id: string) => {
    await markUnread(id);
    invalidate();
  };
  const handleClear = async (id: string) => {
    await archive(id);
    invalidate();
  };
  const handleMarkAllRead = async () => {
    await markAllRead();
    invalidate();
    await refetch();
  };
  const handleClearAll = async () => {
    try {
      await archiveAll();
      invalidate();
    } catch {
      invalidate(); // Refresh anyway so user sees current state
    }
  };

  const handleSelectedChange = (id: string, checked: boolean) => {
    setSelectedIds((prev) => {
      if (checked) return prev.includes(id) ? prev : [...prev, id];
      return prev.filter((x) => x !== id);
    });
  };

  // No prompt, and no countdown either (D7, S6-09). This is the reader's OWN
  // notification, one of a list they can already Clear beside this button with no
  // prompt at all; a dialog or a ten-second window would be the heaviest gesture in
  // the panel guarding its lightest action.
  const handleDeleteOne = async (id: string) => {
    try {
      await deleteNotification(id);
      toast.success('Deleted');
      setSelectedIds((prev) => prev.filter((x) => x !== id));
      invalidate();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to delete');
    }
  };

  const runDeleteSelected = async () => {
    if (selectedIds.length === 0) return;
    try {
      const { count } = await deleteNotificationsBulk(selectedIds);
      toast.success(count === 1 ? 'Deleted' : `Deleted (${count})`);
      setSelectedIds([]);
      setConfirmBulk(null);
      invalidate();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to delete');
    }
  };

  const runDeleteAll = async () => {
    try {
      const { count } = await deleteAllNotifications();
      toast.success(count === 0 ? 'Nothing to delete' : count === 1 ? 'Deleted' : `Deleted (${count})`);
      setSelectedIds([]);
      setConfirmBulk(null);
      invalidate();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to delete all');
    }
  };

  const items = listData?.data ?? [];
  const showUnreadDot = unreadCount > 0;
  const selectedCount = selectedIds.length;

  const visibleIds = useMemo(() => items.map((i) => i.id), [items]);
  const allVisibleSelected =
    items.length > 0 && visibleIds.every((id) => selectedIds.includes(id));
  const someVisibleSelected =
    items.length > 0 &&
    visibleIds.some((id) => selectedIds.includes(id)) &&
    !allVisibleSelected;

  const deleteHint =
    items.length === 0
      ? 'No notifications'
      : selectedCount > 0
        ? `Delete ${selectedCount} selected`
        : 'Delete all';

  return (
    <>
      <Sheet open={open} onOpenChange={setOpen} modal={false}>
        <SheetTrigger asChild>
          <span className="relative inline-flex">
            {trigger}
            {showUnreadDot && (
              <span
                className="absolute -top-0.5 -right-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-medium text-destructive-foreground"
                aria-label={`${unreadCount} unread notifications`}
              >
                {unreadCount > 99 ? '99+' : unreadCount}
              </span>
            )}
          </span>
        </SheetTrigger>
        {/* Passive utility panel: no scrim (D8). */}
        <SheetContent overlay={false} className="p-0 gap-0 sm:w-[500px] sm:max-w-none inset-5 start-auto h-auto rounded-lg p-0 sm:max-w-none [&_[data-slot=sheet-close]]:top-4.5 [&_[data-slot=sheet-close]]:end-5">
          <SheetHeader className="mb-0 flex flex-row items-center gap-2 space-y-0 px-3 py-3 pe-12 text-start border-b border-border">
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="shrink-0 size-8 text-muted-foreground hover:text-destructive hover:bg-destructive/10"
              disabled={items.length === 0}
              aria-label={deleteHint}
              title={deleteHint}
              onClick={() =>
                setConfirmBulk(selectedCount > 0 ? 'selected' : 'all')
              }
            >
              <Trash2 className="size-4" />
            </Button>
            <SheetTitle className="p-0 text-base leading-none">Notifications</SheetTitle>
          </SheetHeader>
          <SheetBody className="p-0">
            <ScrollArea className="h-[calc(100vh-12rem)] min-h-[200px]">
              <Tabs
                value={tab}
                onValueChange={(v) => setTab(v as 'inbox' | 'archived')}
                className="w-full relative"
              >
                <TabsList variant="line" className="w-full px-5 mb-0">
                  <TabsTrigger value="inbox" className="relative">
                    Latest
                    {showUnreadDot && (
                      <div className="w-1.5 h-1.5 rounded-full bg-green-500 absolute top-1 -end-1" />
                    )}
                  </TabsTrigger>
                  <TabsTrigger value="archived">Cleared</TabsTrigger>
                </TabsList>

                {!isLoading && items.length > 0 ? (
                  <div className="flex items-start gap-2.5 px-5 py-2 border-b border-border">
                    <div className="pt-0.5 shrink-0">
                      <Checkbox
                        id="notifications-select-all"
                        size="md"
                        checked={
                          allVisibleSelected
                            ? true
                            : someVisibleSelected
                              ? 'indeterminate'
                              : false
                        }
                        onCheckedChange={(c) => {
                          if (c === true) {
                            setSelectedIds(items.map((i) => i.id));
                          } else {
                            setSelectedIds((prev) =>
                              prev.filter((id) => !visibleIds.includes(id)),
                            );
                          }
                        }}
                        aria-label="Select all on this tab"
                      />
                    </div>
                    <label
                      htmlFor="notifications-select-all"
                      className="text-xs text-muted-foreground leading-5 pt-0.5 cursor-pointer select-none"
                    >
                      Select all
                    </label>
                  </div>
                ) : null}

                <TabsContent value="inbox" className="mt-0">
                  <div className="flex flex-col divide-y divide-border">
                    {isLoading ? (
                      <div className="px-5 py-8 text-sm text-muted-foreground text-center">
                        Loading…
                      </div>
                    ) : items.length === 0 ? (
                      <div className="px-5 py-8 text-sm text-muted-foreground text-center">
                        No notifications
                      </div>
                    ) : (
                      items.map((item) => (
                        <NotificationItem
                          key={item.id}
                          item={item}
                          onMarkRead={handleMarkRead}
                          onMarkUnread={handleMarkUnread}
                          onClear={handleClear}
                          onDelete={handleDeleteOne}
                          onInvalidate={invalidate}
                          selected={selectedIds.includes(item.id)}
                          onSelectedChange={handleSelectedChange}
                        />
                      ))
                    )}
                  </div>
                </TabsContent>

                <TabsContent value="archived" className="mt-0">
                  <div className="flex flex-col divide-y divide-border">
                    {isLoading ? (
                      <div className="px-5 py-8 text-sm text-muted-foreground text-center">
                        Loading…
                      </div>
                    ) : items.length === 0 ? (
                      <div className="px-5 py-8 text-sm text-muted-foreground text-center">
                        No cleared notifications
                      </div>
                    ) : (
                      items.map((item) => (
                        <NotificationItem
                          key={item.id}
                          item={item}
                          onMarkRead={handleMarkRead}
                          onMarkUnread={handleMarkUnread}
                          onClear={handleClear}
                          onDelete={handleDeleteOne}
                          onInvalidate={invalidate}
                          selected={selectedIds.includes(item.id)}
                          onSelectedChange={handleSelectedChange}
                        />
                      ))
                    )}
                  </div>
                </TabsContent>
              </Tabs>
            </ScrollArea>
          </SheetBody>
          <SheetFooter className="border-t border-border p-4 flex flex-col gap-2 min-w-0">
            <div className="grid grid-cols-2 gap-2 w-full min-w-0">
              <Button size="sm" variant="outline" className="min-w-0 truncate" onClick={handleClearAll}>
                Clear all
              </Button>
              <Button size="sm" variant="outline" className="min-w-0 truncate" onClick={handleMarkAllRead}>
                Read all
              </Button>
            </div>
          </SheetFooter>
        </SheetContent>
      </Sheet>

      <AlertDialog
        open={confirmBulk !== null}
        onOpenChange={(o) => {
          if (!o) setConfirmBulk(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {confirmBulk === 'selected'
                ? `Delete ${selectedCount} selected?`
                : 'Delete all notifications?'}
            </AlertDialogTitle>
            <AlertDialogDescription>
              Permanent. Can&apos;t undo.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() =>
                void (confirmBulk === 'selected' ? runDeleteSelected() : runDeleteAll())
              }
            >
              {confirmBulk === 'selected' ? 'Delete selected' : 'Delete all'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
