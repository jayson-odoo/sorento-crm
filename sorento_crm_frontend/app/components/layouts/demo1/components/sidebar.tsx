'use client';

import { usePathname } from 'next/navigation';
import { ChevronFirst } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useSettings } from '@/providers/settings-provider';
import { Button } from '@/components/ui/button';
import { SidebarHeader } from './sidebar-header';
import { SidebarMenu } from './sidebar-menu';

export function Sidebar() {
  const { settings, storeOption } = useSettings();
  const pathname = usePathname();

  const handleToggleClick = () => {
    storeOption(
      'layouts.demo1.sidebarCollapse',
      !settings.layouts.demo1.sidebarCollapse,
    );
  };

  return (
    // The collapse toggle scales THIS box (`transform` only, css/demos/demo1.css
    // - S8-03); `origin-left` is where that scale grows/shrinks from, so the
    // clip always keeps the LEFT edge (the icon column) and hides the right
    // (the labels), never the reverse.
    <div
      className={cn(
        'sidebar material-thick lg:border-e lg:border-border lg:fixed lg:top-[var(--impersonation-banner-height,0px)] lg:bottom-0 lg:z-(--z-sidebar) lg:flex origin-left rtl:origin-right shrink-0',
        (settings.layouts.demo1.sidebarTheme === 'dark' ||
          pathname.includes('dark-sidebar')) &&
          'dark',
      )}
    >
      {/* Counter-scales against `.sidebar`'s own transform in lockstep (demo1.css)
          so the header + menu never visually stretch or squash while it collapses.
          Its own `overflow: hidden` (demo1.css) clips that spillover - the
          toggle below is a SIBLING of this, specifically so it sits outside
          that clip and can still float past the sidebar's edge. */}
      <div className="sidebar-rail flex h-full flex-col items-stretch origin-left rtl:origin-right">
        <SidebarHeader />
        <div className="overflow-hidden">
          <div className="w-(--sidebar-default-width)">
            <SidebarMenu />
          </div>
        </div>
      </div>
      <Button
        onClick={handleToggleClick}
        size="sm"
        mode="icon"
        variant="outline"
        className={cn(
          'hidden lg:flex size-7 absolute start-full top-[calc(var(--header-height)/2)] rtl:translate-x-2/4 -translate-x-2/4 -translate-y-1/2',
          // No counter-counter-scale needed here (contrast the old version
          // nested inside `.sidebar-rail`, sidebar-header.tsx history): a
          // direct child of `.sidebar` is already subject to exactly ONE
          // scale, `.sidebar`'s own, which is exactly "shrinks and moves with
          // the real edge" - the behaviour S8-03 wanted, minus the clip.
          settings.layouts.demo1.sidebarCollapse
            ? 'ltr:rotate-180'
            : 'rtl:rotate-180',
        )}
      >
        <ChevronFirst className="size-4!" />
      </Button>
    </div>
  );
}
