'use client';

import { AppsDropdownMenu } from '@/partials/topbar/apps-dropdown-menu';
import { ChatSheet } from '@/partials/topbar/chat-sheet';
import { UserDropdownMenu } from '@/partials/topbar/user-dropdown-menu';
import { SessionUserAvatar } from '@/partials/topbar/session-user-avatar';
import { LayoutGrid, MessageCircleMore } from 'lucide-react';
import { Button } from '@/components/ui/button';

export function SidebarFooter() {
  return (
    <div className="flex flex-col gap-5 items-center shrink-0 pb-5">
      <div className="flex flex-col gap-1.5">
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
        <AppsDropdownMenu
          trigger={
            <Button
              variant="ghost"
              mode="icon"
              className="hover:bg-background hover:[&_svg]:text-primary"
            >
              <LayoutGrid className="size-4.5!" />
            </Button>
          }
        />
      </div>

      <UserDropdownMenu
        trigger={
          <SessionUserAvatar className="size-8 rounded-lg border-2 border-mono/30 shrink-0 cursor-pointer object-cover" />
        }
      />
    </div>
  );
}
