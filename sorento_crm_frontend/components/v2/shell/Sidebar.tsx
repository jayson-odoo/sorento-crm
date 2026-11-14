'use client';

import Link from 'next/link';
import { MENU_SIDEBAR } from '@/config/menu.config';
import { SidebarMenu } from '@/app/components/layouts/demo1/components/sidebar-menu';
import { toAbsoluteUrl } from '@/lib/helpers';

/**
 * The v2 desktop sidebar (E-1): the same MENU_SIDEBAR config and the same permission-filtered
 * menu renderer as v1, so both versions always offer the same pages.
 */
export function Sidebar() {
  return (
    <aside
      aria-label="Main navigation"
      className="fixed start-0 bottom-0 top-(--system-banner-height,0px) z-(--z-sidebar) flex w-(--v2-sidebar-width) flex-col border-e border-border bg-background"
    >
      <div className="flex h-14 shrink-0 items-center px-5">
        <Link href="/" className="shrink-0">
          <img src={toAbsoluteUrl('/media/app/sorento-logo.svg')} className="h-[22px] w-auto dark:hidden" alt="Sorento" />
          <img
            src={toAbsoluteUrl('/media/app/sorento-logo-dark.svg')}
            className="hidden h-[22px] w-auto dark:inline"
            alt="Sorento"
          />
        </Link>
      </div>
      <div className="min-h-0 grow overflow-y-auto">
        <SidebarMenu menu={MENU_SIDEBAR} />
      </div>
    </aside>
  );
}
