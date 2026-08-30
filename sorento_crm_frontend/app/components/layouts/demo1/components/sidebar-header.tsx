'use client';

import Link from 'next/link';
import { ChevronFirst } from 'lucide-react';
import { toAbsoluteUrl } from '@/lib/helpers';
import { cn } from '@/lib/utils';
import { useSettings } from '@/providers/settings-provider';
import { Button } from '@/components/ui/button';

export function SidebarHeader() {
  const { settings, storeOption } = useSettings();

  const handleToggleClick = () => {
    storeOption(
      'layouts.demo1.sidebarCollapse',
      !settings.layouts.demo1.sidebarCollapse,
    );
  };

  return (
    <div className="sidebar-header hidden lg:flex items-center relative justify-between px-3 lg:px-6 shrink-0">
      <Link
        href="/"
        className={cn(
          'min-w-0 shrink flex items-center',
          settings.layouts.demo1.sidebarCollapse ? 'justify-center' : 'justify-start',
        )}
      >
        <div className="dark:hidden">
          <img
            src={toAbsoluteUrl('/media/app/sorento-logo.svg')}
            className="default-logo h-[22px] w-auto max-w-[200px]"
            alt="Sorento"
          />
          <img
            src={toAbsoluteUrl('/media/app/sorento-mark.svg')}
            className="small-logo h-8 w-8 shrink-0"
            alt="Sorento"
          />
        </div>
        <div className="hidden dark:block">
          <img
            src={toAbsoluteUrl('/media/app/sorento-logo-dark.svg')}
            className="default-logo h-[22px] w-auto max-w-[200px]"
            alt="Sorento"
          />
          <img
            src={toAbsoluteUrl('/media/app/sorento-mark-dark.svg')}
            className="small-logo h-8 w-8 shrink-0"
            alt="Sorento"
          />
        </div>
      </Link>
      <Button
        onClick={handleToggleClick}
        size="sm"
        mode="icon"
        variant="outline"
        className={cn(
          'size-7 absolute start-full top-2/4 rtl:translate-x-2/4 -translate-x-2/4 -translate-y-2/4 origin-left rtl:origin-right',
          // `.sidebar-header` sits inside `.sidebar-rail`, which counter-scales
          // against `.sidebar`'s own collapse transform so its content never
          // visually distorts (S8-03, css/demos/demo1.css). This button is the
          // one thing in there that SHOULD track `.sidebar`'s real (shrunk) edge
          // rather than stay full-size - re-applying the same scale cancels the
          // rail's counter-scale for just this element, so it shrinks and moves
          // with the edge instead of floating over the content past it.
          'scale-x-[var(--sidebar-scale,1)]',
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
