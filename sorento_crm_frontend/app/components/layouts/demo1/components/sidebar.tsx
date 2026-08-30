'use client';

import { usePathname } from 'next/navigation';
import { cn } from '@/lib/utils';
import { useSettings } from '@/providers/settings-provider';
import { SidebarHeader } from './sidebar-header';
import { SidebarMenu } from './sidebar-menu';

export function Sidebar() {
  const { settings } = useSettings();
  const pathname = usePathname();

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
          so the header + menu never visually stretch or squash while it collapses. */}
      <div className="sidebar-rail flex h-full flex-col items-stretch origin-left rtl:origin-right">
        <SidebarHeader />
        <div className="overflow-hidden">
          <div className="w-(--sidebar-default-width)">
            <SidebarMenu />
          </div>
        </div>
      </div>
    </div>
  );
}
