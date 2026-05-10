"use client";

import { useEffect } from 'react';
import Link from 'next/link';
import { LogOut, UserCog } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { useImpersonation } from '@/hooks/useImpersonation';

const BANNER_HEIGHT = 40;

export function ImpersonationBanner() {
  const { session, stop, stopping } = useImpersonation();

  useEffect(() => {
    if (typeof document === 'undefined') return;
    const root = document.documentElement;
    if (session) {
      root.style.setProperty('--impersonation-banner-height', `${BANNER_HEIGHT}px`);
      document.body.style.paddingTop = `${BANNER_HEIGHT}px`;
    } else {
      root.style.removeProperty('--impersonation-banner-height');
      document.body.style.paddingTop = '';
    }
    return () => {
      if (typeof document === 'undefined') return;
      document.body.style.paddingTop = '';
      document.documentElement.style.removeProperty('--impersonation-banner-height');
    };
  }, [session]);

  if (!session) return null;

  const onExit = async () => {
    try {
      await stop();
    } finally {
      // Hard reload so sidebar, permissions, and listings refetch as the real admin.
      if (typeof window !== 'undefined') {
        window.location.reload();
      }
    }
  };

  const targetName = session.targetUser.name || session.targetUser.email || session.targetUser.id;

  return (
    <div
      role="status"
      data-testid="impersonation-banner"
      className="fixed inset-x-0 top-0 z-[60] w-screen border-b border-amber-300 bg-amber-100 px-4 py-2 text-amber-900 shadow-sm"
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm">
          <UserCog className="size-4 shrink-0" aria-hidden />
          <span>
            You are currently impersonating{' '}
            <Link
              href={`/user-management/users/${session.targetUser.id}`}
              className="font-semibold underline underline-offset-2 hover:text-amber-950"
            >
              {targetName}
            </Link>
            . Records you create or modify are still attributed to you.
          </span>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={onExit}
          disabled={stopping}
          className="border-amber-400 bg-white text-amber-900 hover:bg-amber-50"
          data-testid="impersonation-exit"
        >
          <LogOut className="mr-1 size-3.5" />
          Exit Impersonation
        </Button>
      </div>
    </div>
  );
}
