'use client';

/**
 * Top-nav icon for Upload Activity. Mirrors NotificationsSheet badge
 * pattern but dispatches drawer open via UploadManager context rather
 * than wrapping a SheetTrigger — the drawer is mounted once at the
 * layout level.
 *
 * Badge count = sessions in (uploading | processing) plus any
 * `needs_action` session. Hidden when zero.
 */

import { Upload } from 'lucide-react';

import { Button } from '@/components/ui/button';

import { useUploadActivity } from './useUploadActivity';
import { useUploadManager } from './UploadManagerContext';

export function UploadActivityIcon() {
  const { setDrawerOpen } = useUploadManager();
  const { badgeCount } = useUploadActivity();

  return (
    <span className="relative inline-flex">
      <Button
        variant="ghost"
        mode="icon"
        shape="circle"
        className="hover:bg-transparent hover:[&_svg]:text-primary"
        onClick={() => setDrawerOpen(true)}
        aria-label={
          badgeCount > 0
            ? `${badgeCount} upload${badgeCount > 1 ? 's' : ''} need attention`
            : 'Upload activity'
        }
        title="Upload activity"
      >
        <Upload className="size-4.5!" />
      </Button>
      {badgeCount > 0 && (
        <span
          className="absolute -top-0.5 -right-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-medium text-destructive-foreground pointer-events-none"
          aria-hidden
        >
          {badgeCount > 99 ? '99+' : badgeCount}
        </span>
      )}
    </span>
  );
}
