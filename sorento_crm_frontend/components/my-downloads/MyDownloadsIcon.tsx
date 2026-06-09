'use client';

/**
 * Top-nav icon for My Downloads. Opens the drawer via context; badge shows the
 * count of in-flight (pending/processing) exports. Hidden when zero.
 */

import { Download } from 'lucide-react';

import { Button } from '@/components/ui/button';

import { useMyDownloads } from './MyDownloadsContext';

export function MyDownloadsIcon() {
  const { setOpen, badgeCount } = useMyDownloads();

  return (
    <span className="relative inline-flex">
      <Button
        variant="ghost"
        mode="icon"
        shape="circle"
        className="hover:bg-transparent hover:[&_svg]:text-primary"
        onClick={() => setOpen(true)}
        aria-label={
          badgeCount > 0
            ? `${badgeCount} download${badgeCount > 1 ? 's' : ''} preparing`
            : 'My downloads'
        }
        title="My downloads"
      >
        <Download className="size-4.5!" />
      </Button>
      {badgeCount > 0 && (
        <span
          className="absolute -top-0.5 -right-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[10px] font-medium text-primary-foreground pointer-events-none"
          aria-hidden
        >
          {badgeCount > 99 ? '99+' : badgeCount}
        </span>
      )}
    </span>
  );
}
