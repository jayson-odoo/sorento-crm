'use client';

import { useEffect, useRef, useState } from 'react';
import { Bell, Menu, MoreHorizontal, Search } from 'lucide-react';
import { SearchDialog } from '@/app/components/partials/dialogs/search/search-dialog';
import { CompanySwitcher } from '@/app/components/partials/topbar/company-switcher';
import { NotificationsSheet } from '@/app/components/partials/topbar/notifications-sheet';
import { UserDropdownMenu } from '@/app/components/partials/topbar/user-dropdown-menu';
import { SessionUserAvatar } from '@/app/components/partials/topbar/session-user-avatar';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { useIsPhone } from './useViewport';

/**
 * The v2 top bar (E-1, playbook P6). 56 px in every state. On a phone, scrolling down condenses
 * it: the right-hand icons fold into one "More actions" button and search narrows to 36 px;
 * scrolling up reverses it. Desktop never condenses.
 */
export function Topbar({ onOpenNav }: { onOpenNav?: () => void }) {
  const isPhone = useIsPhone();
  const [scrolledDown, setScrolledDown] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const lastY = useRef(0);

  useEffect(() => {
    if (!isPhone) {
      setScrolledDown(false);
      return;
    }
    const onScroll = () => {
      const y = window.scrollY;
      if (y > lastY.current && y > 0) setScrolledDown(true);
      else if (y < lastY.current) {
        setScrolledDown(false);
        setExpanded(false);
      }
      lastY.current = y;
    };
    lastY.current = window.scrollY;
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, [isPhone]);

  const condensed = isPhone && scrolledDown;
  const showParts = !condensed || expanded;

  return (
    <header
      data-testid="topbar"
      data-condensed={condensed ? 'true' : 'false'}
      className="sticky top-(--system-banner-height,0px) z-(--z-header) flex h-14 shrink-0 items-center gap-2 border-b border-border bg-background px-4"
    >
      {isPhone && (
        <Button variant="ghost" mode="icon" aria-label="Open navigation" onClick={onOpenNav} className="size-11">
          <Menu className="size-5" />
        </Button>
      )}
      <div data-slot="topbar-search" className={cn('flex min-w-0 grow items-center', condensed ? 'h-9' : isPhone ? 'h-11' : 'h-9')}>
        <SearchDialog
          trigger={
            <Button
              variant="outline"
              className={cn('h-full justify-start gap-2 px-3 text-muted-foreground', isPhone ? 'w-full' : 'w-72')}
              aria-label="Search"
            >
              <Search className="size-4 shrink-0" />
              <span className="truncate">Search</span>
            </Button>
          }
        />
      </div>
      <div className="ms-auto flex shrink-0 items-center gap-1.5">
        {showParts ? (
          <>
            <CompanySwitcher />
            <NotificationsSheet
              trigger={
                <Button variant="ghost" mode="icon" shape="circle" aria-label="Notifications" className="size-9">
                  <Bell className="size-4.5" />
                </Button>
              }
            />
            <UserDropdownMenu trigger={<SessionUserAvatar className="size-9 shrink-0 cursor-pointer rounded-full" />} />
          </>
        ) : (
          <Button variant="ghost" mode="icon" aria-label="More actions" className="size-11" onClick={() => setExpanded(true)}>
            <MoreHorizontal className="size-5" />
          </Button>
        )}
      </div>
    </header>
  );
}
