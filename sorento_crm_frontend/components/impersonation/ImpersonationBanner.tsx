"use client";

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { ChevronDown, ChevronUp, LogOut, UserCog } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { useImpersonation } from '@/hooks/useImpersonation';

const BANNER_HEIGHT = 40;
const COLLAPSE_KEY = 'sorento.impersonationBannerCollapsed';

export function ImpersonationBanner() {
  const { session, stop, stopping } = useImpersonation();
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false;
    return window.localStorage.getItem(COLLAPSE_KEY) === '1';
  });

  useEffect(() => {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem(COLLAPSE_KEY, collapsed ? '1' : '0');
  }, [collapsed]);

  useEffect(() => {
    if (typeof document === 'undefined') return;
    const root = document.documentElement;
    if (session && !collapsed) {
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
  }, [session, collapsed]);

  if (!session) return null;

  const onExit = async () => {
    try {
      await stop();
    } finally {
      if (typeof window !== 'undefined') {
        window.location.reload();
      }
    }
  };

  const targetName = session.targetUser.name || session.targetUser.email || session.targetUser.id;

  if (collapsed) {
    return (
      <button
        type="button"
        onClick={() => setCollapsed(false)}
        className="fixed right-3 top-2 z-[60] flex items-center gap-1 rounded-full border border-amber-300 bg-amber-100 px-2.5 py-1 text-xs font-medium text-amber-900 shadow-sm hover:bg-amber-200"
        title="Show impersonation banner"
        data-testid="impersonation-banner-show"
      >
        <UserCog className="size-3.5" aria-hidden />
        Impersonating
        <ChevronDown className="size-3.5" aria-hidden />
      </button>
    );
  }

  return (
    <div
      role="status"
      data-testid="impersonation-banner"
      className="fixed inset-x-0 top-0 z-[60] w-screen border-b border-amber-300 bg-amber-100 px-4 py-2 text-amber-900 shadow-sm"
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2 text-sm">
          <UserCog className="size-4 shrink-0" aria-hidden />
          <span className="truncate">
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
        <div className="flex items-center gap-2">
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
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setCollapsed(true)}
            className="text-amber-900 hover:bg-amber-200"
            title="Hide banner"
            data-testid="impersonation-collapse"
          >
            <ChevronUp className="size-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
