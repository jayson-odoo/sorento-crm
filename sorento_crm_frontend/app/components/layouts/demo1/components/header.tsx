'use client';

import { useEffect, useState } from 'react';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { SearchDialog } from '@/partials/dialogs/search/search-dialog';
import { AppsDropdownMenu } from '@/partials/topbar/apps-dropdown-menu';
import { NotificationsSheet } from '@/partials/topbar/notifications-sheet';
import { UserDropdownMenu } from '@/partials/topbar/user-dropdown-menu';
import { SessionUserAvatar } from '@/partials/topbar/session-user-avatar';
import { UploadActivityIcon } from '@/components/upload-activity';
import { MyDownloadsIcon } from '@/components/my-downloads/MyDownloadsIcon';
import {
  Bell,
  LayoutGrid,
  Menu,
  Search,
  SquareChevronRight,
} from 'lucide-react';
import { toAbsoluteUrl } from '@/lib/helpers';
import { cn } from '@/lib/utils';
import { useIsMobile } from '@/hooks/use-mobile';
import { useScrollPosition } from '@/hooks/use-scroll-position';
import { Button } from '@/components/ui/button';
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet';
import { Container } from '@/components/common/container';
import { StoreClientTopbar } from '@/app/(protected)/store-client/components/common/topbar';
import { Breadcrumb } from './breadcrumb';
import { MegaMenu } from './mega-menu';
import { MegaMenuMobile } from './mega-menu-mobile';
import { SidebarMenu } from './sidebar-menu';

/** Compact shortcut label for search: ⌘⇧K on Mac, Ctrl+⇧K on Windows/Linux. */
function getSearchShortcutLabel(): string {
  if (typeof navigator === 'undefined') return '⌘⇧K';
  return /Mac|iPod|iPhone|iPad/.test(navigator.platform) ? '⌘⇧K' : 'Ctrl+⇧K';
}

export function Header() {
  const [isSidebarSheetOpen, setIsSidebarSheetOpen] = useState(false);
  const [isMegaMenuSheetOpen, setIsMegaMenuSheetOpen] = useState(false);
  const [searchShortcut, setSearchShortcut] = useState('⌘⇧K');
  useEffect(() => {
    setSearchShortcut(getSearchShortcutLabel());
  }, []);

  const pathname = usePathname();
  const mobileMode = useIsMobile();

  const scrollPosition = useScrollPosition();
  const headerSticky: boolean = scrollPosition > 0;

  // Close sheet when route changes
  useEffect(() => {
    setIsSidebarSheetOpen(false);
    setIsMegaMenuSheetOpen(false);
  }, [pathname]);

  return (
    <header
      className={cn(
        'header fixed top-0 z-10 start-0 flex items-stretch shrink-0 border-b border-transparent bg-background end-0 pe-[var(--removed-body-scroll-bar-size,0px)]',
        headerSticky && 'border-b border-border',
      )}
    >
      <Container className="flex justify-between items-stretch lg:gap-4">
        {/* HeaderLogo */}
        <div className="flex gap-1 lg:hidden items-center gap-2.5">
          <Link href="/" className="shrink-0">
            <img
              src={toAbsoluteUrl('/media/app/sorento-logo.svg')}
              className="h-[22px] w-auto max-w-[140px] dark:hidden"
              alt="Sorento"
            />
            <img
              src={toAbsoluteUrl('/media/app/sorento-logo-dark.svg')}
              className="h-[22px] w-auto max-w-[140px] hidden dark:inline"
              alt="Sorento"
            />
          </Link>
          <div className="flex items-center">
            {mobileMode && (
              <Sheet
                open={isSidebarSheetOpen}
                onOpenChange={setIsSidebarSheetOpen}
              >
                <SheetTrigger asChild>
                  <Button variant="ghost" mode="icon">
                    <Menu className="text-muted-foreground/70" />
                  </Button>
                </SheetTrigger>
                <SheetContent
                  className="p-0 gap-0 w-[275px]"
                  side="left"
                  close={false}
                >
                  <SheetTitle className="sr-only">Navigation menu</SheetTitle>
                  <SheetHeader className="p-0 space-y-0" />
                  <SheetBody className="p-0 overflow-y-auto">
                    <SidebarMenu />
                  </SheetBody>
                </SheetContent>
              </Sheet>
            )}
            {mobileMode && (
              <Sheet
                open={isMegaMenuSheetOpen}
                onOpenChange={setIsMegaMenuSheetOpen}
              >
                <SheetTrigger asChild>
                  <Button variant="ghost" mode="icon">
                    <SquareChevronRight className="text-muted-foreground/70" />
                  </Button>
                </SheetTrigger>
                <SheetContent
                  className="p-0 gap-0 w-[275px]"
                  side="left"
                  close={false}
                >
                  <SheetTitle className="sr-only">Menu</SheetTitle>
                  <SheetHeader className="p-0 space-y-0" />
                  <SheetBody className="p-0 overflow-y-auto">
                    <MegaMenuMobile />
                  </SheetBody>
                </SheetContent>
              </Sheet>
            )}
          </div>
        </div>

        {/* Main Content (MegaMenu or Breadcrumbs) */}
        {pathname.startsWith('/account') ? (
          <Breadcrumb />
        ) : (
          !mobileMode && <MegaMenu />
        )}

        {/* HeaderTopbar */}
        <div className="flex items-center gap-3">
          {pathname.startsWith('/store-client') ? (
            <StoreClientTopbar />
          ) : (
            <>
              {!mobileMode && (
                <SearchDialog
                  trigger={
                    <Button
                      variant="outline"
                      className="h-9 w-60 justify-between px-3 text-muted-foreground hover:text-foreground"
                      title="Open search (Cmd+Shift+K or Ctrl+Shift+K)"
                    >
                      <span className="inline-flex min-w-0 flex-1 items-center gap-2 truncate">
                        <Search className="size-4 shrink-0" />
                        <span className="truncate">Search menu...</span>
                      </span>
                      <span
                        className="shrink-0 text-[11px] text-muted-foreground"
                        title="Cmd+Shift+K or Ctrl+Shift+K"
                      >
                        {searchShortcut}
                      </span>
                    </Button>
                  }
                />
              )}
              {/* Secondary icons (uploads / downloads / apps) declutter the mobile
                  header — they're still reachable from the sidebar / menus. */}
              {!mobileMode && <UploadActivityIcon />}
              {!mobileMode && <MyDownloadsIcon />}
              <NotificationsSheet
                trigger={
                  <Button
                    variant="ghost"
                    mode="icon"
                    shape="circle"
                    className="size-9 hover:bg-primary/10 hover:[&_svg]:text-primary"
                  >
                    <Bell className="size-4.5!" />
                  </Button>
                }
              />
              {!mobileMode && (
                <AppsDropdownMenu
                  trigger={
                    <Button
                      variant="ghost"
                      mode="icon"
                      shape="circle"
                      className="size-9 hover:bg-primary/10 hover:[&_svg]:text-primary"
                    >
                      <LayoutGrid className="size-4.5!" />
                    </Button>
                  }
                />
              )}
              <UserDropdownMenu
                trigger={
                  <SessionUserAvatar className="size-9 rounded-full border-2 border-green-500 shrink-0 cursor-pointer" />
                }
              />
            </>
          )}
        </div>
      </Container>
    </header>
  );
}
