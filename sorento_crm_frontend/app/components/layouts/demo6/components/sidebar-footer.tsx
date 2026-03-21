'use client';

import { ChatSheet } from '@/partials/topbar/chat-sheet';
import { NotificationsSheet } from '@/partials/topbar/notifications-sheet';
import { UserDropdownMenu } from '@/partials/topbar/user-dropdown-menu';
import { SessionUserAvatar } from '@/partials/topbar/session-user-avatar';
import { MessageCircleMore, MessageSquareDot } from 'lucide-react';
import { Button } from '@/components/ui/button';

export function SidebarFooter() {
  return (
    <div className="flex flex-center justify-between shrink-0 ps-4 pe-3.5 h-14">
      <UserDropdownMenu
        trigger={
          <SessionUserAvatar className="size-9 rounded-full border-2 border-secondary shrink-0 cursor-pointer object-cover" />
        }
      />

      <div className="flex flex-center gap-1.5">
        <NotificationsSheet
          trigger={
            <Button
              variant="ghost"
              mode="icon"
              className="hover:bg-background hover:[&_svg]:text-primary"
            >
              <MessageSquareDot className="size-4.5!" />
            </Button>
          }
        />
        <ChatSheet
          trigger={
            <Button
              variant="ghost"
              mode="icon"
              className="hover:bg-background hover:[&_svg]:text-primary"
            >
              <MessageCircleMore className="size-4.5!" />
            </Button>
          }
        />
      </div>
    </div>
  );
}
