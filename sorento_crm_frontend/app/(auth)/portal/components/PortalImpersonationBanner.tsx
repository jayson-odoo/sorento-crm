'use client';

import { useEffect, useState } from 'react';
import { ChevronDown, ChevronUp, LogOut, UserCog } from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  PortalImpersonationInfo,
  clearImpersonationToken,
  fetchMe,
  readPortalToken,
  stopPortalImpersonation,
} from '../lib/portal-client';

const COLLAPSE_KEY = 'sorento.portalImpersonationBannerCollapsed';

export function PortalImpersonationBanner() {
  const [info, setInfo] = useState<PortalImpersonationInfo | null>(null);
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false;
    return window.localStorage.getItem(COLLAPSE_KEY) === '1';
  });
  const [exiting, setExiting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      if (!readPortalToken()) {
        if (!cancelled) setInfo(null);
        return;
      }
      try {
        const me = await fetchMe();
        if (!cancelled) setInfo(me.impersonation ?? null);
      } catch {
        if (!cancelled) setInfo(null);
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem(COLLAPSE_KEY, collapsed ? '1' : '0');
  }, [collapsed]);

  useEffect(() => {
    if (typeof document === 'undefined') return;
    const body = document.body;
    if (info && !collapsed) {
      body.style.paddingTop = '40px';
    } else {
      body.style.paddingTop = '';
    }
    return () => {
      body.style.paddingTop = '';
    };
  }, [info, collapsed]);

  if (!info) return null;

  const adminLabel = info.admin_name || info.admin_email || info.admin_user_id;

  const onExit = async () => {
    setExiting(true);
    try {
      await stopPortalImpersonation();
    } catch {
      // ignore — token revoke is best-effort
    } finally {
      // Session-scoped clear only: the admin's own device-trust token (if they
      // are also a portal contact on this browser) must survive the exit.
      clearImpersonationToken();
      if (typeof window !== 'undefined') {
        window.location.href = '/';
      }
    }
  };

  if (collapsed) {
    return (
      <button
        type="button"
        onClick={() => setCollapsed(false)}
        className="fixed right-3 top-2 z-[60] flex items-center gap-1 rounded-full border border-amber-300 bg-amber-100 px-2.5 py-1 text-xs font-medium text-amber-900 shadow-sm hover:bg-amber-200"
        title="Show impersonation banner"
        data-testid="portal-impersonation-banner-show"
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
      data-testid="portal-impersonation-banner"
      className="fixed inset-x-0 top-0 z-[60] w-screen border-b border-amber-300 bg-amber-100 px-4 py-2 text-amber-900 shadow-sm"
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2 text-sm">
          <UserCog className="size-4 shrink-0" aria-hidden />
          <span className="truncate">
            Admin <strong>{adminLabel}</strong> is viewing this portal as you.
          </span>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={onExit}
            disabled={exiting}
            className="border-amber-400 bg-white text-amber-900 hover:bg-amber-50"
            data-testid="portal-impersonation-exit"
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
            data-testid="portal-impersonation-collapse"
          >
            <ChevronUp className="size-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
