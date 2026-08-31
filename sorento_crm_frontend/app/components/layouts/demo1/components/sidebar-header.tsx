'use client';

import Link from 'next/link';
import { toAbsoluteUrl } from '@/lib/helpers';
import { cn } from '@/lib/utils';
import { useSettings } from '@/providers/settings-provider';

/**
 * The collapse toggle used to render here too, but it floats HALF outside the
 * sidebar's own edge on purpose (a straddling circle) - which put it inside
 * this component's clipped ancestor (`.sidebar-rail`, demo1.css) once S8-03
 * added that clip for the counter-scale trick. It now lives in `sidebar.tsx`,
 * a sibling of the rail, so it is never inside that clip. See `Sidebar()`.
 */
export function SidebarHeader() {
  const { settings } = useSettings();

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
    </div>
  );
}
