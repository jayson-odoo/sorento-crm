'use client';

import { usePathname } from 'next/navigation';
import { SearchDialog } from '@/partials/dialogs/search/search-dialog';
import { ChatSheet } from '@/partials/topbar/chat-sheet';
import { NotificationsSheet } from '@/partials/topbar/notifications-sheet';
import { UserDropdownMenu } from '@/partials/topbar/user-dropdown-menu';
import { SessionUserAvatar } from '@/partials/topbar/session-user-avatar';
import { MessageCircleMore, MessageSquareDot, Search } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { StoreClientTopbar } from '@/app/(protected)/store-client/components/common/topbar';

export function HeaderTopbar() {
  const pathname = usePathname();

  return (
    <>
      {pathname.startsWith('/store-client') ? (
        <StoreClientTopbar />
      ) : (
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-3">
            <SearchDialog
              trigger={
                <Button
                  variant="ghost"
                  mode="icon"
                  shape="circle"
                  className="size-9"
                >
                  <Search className="size-4.5!" />
                </Button>
              }
            />
            <ChatSheet
              trigger={
                <Button
                  variant="ghost"
                  mode="icon"
                  shape="circle"
                  className="size-9"
                >
                  <MessageCircleMore className="size-4.5!" />
                </Button>
              }
            />
            <NotificationsSheet
              trigger={
                <Button
                  variant="ghost"
                  mode="icon"
                  size="sm"
                  shape="circle"
                  className="size-9"
                >
                  <MessageSquareDot className="size-4.5!" />
                </Button>
              }
            />
          </div>
          <UserDropdownMenu
            trigger={
              <SessionUserAvatar className="cursor-pointer size-9 rounded-full justify-center border border-gray-500 shrink-0" />
            }
          />
        </div>
      )}
    </>
  );
}
