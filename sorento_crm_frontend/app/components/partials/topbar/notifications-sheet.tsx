'use client';

import { ReactNode, useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Bell } from 'lucide-react';
import { Button } from '@/components/ui/button';
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
  listNotifications,
  getUnreadCount,
  markRead,
  markUnread,
  markAllRead,
  archive,
  archiveAll,
} from '@/services/notificationService';
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

  const items = listData?.data ?? [];
  const showUnreadDot = unreadCount > 0;

  return (
    <Sheet open={open} onOpenChange={setOpen}>
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
      <SheetContent className="p-0 gap-0 sm:w-[500px] sm:max-w-none inset-5 start-auto h-auto rounded-lg p-0 sm:max-w-none [&_[data-slot=sheet-close]]:top-4.5 [&_[data-slot=sheet-close]]:end-5">
        <SheetHeader className="mb-0">
          <SheetTitle className="p-3">Notifications</SheetTitle>
        </SheetHeader>
        <SheetBody className="p-0">
          <ScrollArea className="h-[calc(100vh-10.5rem)]">
            <Tabs
              value={tab}
              onValueChange={(v) => setTab(v as 'inbox' | 'archived')}
              className="w-full relative"
            >
              <TabsList variant="line" className="w-full px-5 mb-5">
                <TabsTrigger value="inbox" className="relative">
                  Latest
                  {showUnreadDot && (
                    <div className="w-1.5 h-1.5 rounded-full bg-green-500 absolute top-1 -end-1" />
                  )}
                </TabsTrigger>
                <TabsTrigger value="archived">Cleared</TabsTrigger>
              </TabsList>

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
                        onInvalidate={invalidate}
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
                        onInvalidate={invalidate}
                      />
                    ))
                  )}
                </div>
              </TabsContent>
            </Tabs>
          </ScrollArea>
        </SheetBody>
        <SheetFooter className="border-t border-border p-5 flex flex-col gap-3">
          <div className="grid grid-cols-2 gap-2.5 w-full">
            <Button variant="outline" onClick={handleClearAll}>
              Clear all
            </Button>
            <Button variant="outline" onClick={handleMarkAllRead}>
              Mark all as read
            </Button>
          </div>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
