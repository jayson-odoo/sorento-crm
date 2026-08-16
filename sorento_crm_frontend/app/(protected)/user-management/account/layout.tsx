'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { AudioLines, ShieldCheck, UserPen } from 'lucide-react';
import { apiFetch } from '@/lib/api';
import { getInitials } from '@/lib/helpers';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Container } from '@/components/common/container';
import { ContentLoader } from '@/components/common/content-loader';
import {
  Toolbar,
  ToolbarActions,
  ToolbarHeading,
  ToolbarTitle,
} from '@/components/common/toolbar';
import { AccountProvider } from './components/account-context';
import { useHasPermission } from '@/hooks/usePermissions';

type NavRoutes = Record<
  string,
  {
    title: string;
    icon: React.FC<React.SVGProps<SVGSVGElement>>;
    path: string;
  }
>;

export default function Layout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();

  const { data: user, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['account-profile'],
    queryFn: async () => {
      const response = await apiFetch('/api/user-management/account/');
      if (!response.ok) {
        const { message } = await response.json();
        throw new Error(message);
      }
      return response.json();
    },
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60, // 60 minutes
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    retry: 1,
  });

  // The logs tab proxies to GET /system-logs, gated on user_management.logs.view -
  // without it the tab is a guaranteed error.
  const canViewLogs = useHasPermission('user_management.logs.view');

  const navRoutes = useMemo<NavRoutes>(
    () => ({
      profile: {
        title: 'Profile',
        icon: UserPen,
        path: '/user-management/account',
      },
      security: {
        title: 'Security',
        icon: ShieldCheck,
        path: '/user-management/account/security',
      },
      ...(canViewLogs
        ? {
            logs: {
              title: 'Logs',
              icon: AudioLines,
              path: '/user-management/account/logs',
            },
          }
        : {}),
    }),
    [canViewLogs],
  );

  // Local state to instantly update the active tab on click
  const [activeTab, setActiveTab] = useState<string>('');

  // Keep the local state in sync with the current pathname, in case navigation happens externally
  useEffect(() => {
    const found = Object.keys(navRoutes).find(
      (key) => pathname === navRoutes[key].path,
    );
    if (found) {
      setActiveTab(found);
    } else {
      setActiveTab('profile');
    }
  }, [navRoutes, pathname]);

  // Handle tab click: update local state immediately and trigger navigation
  const handleTabClick = (key: string, path: string) => {
    setActiveTab(key);
    // Navigate after a short delay (or immediately) so that the UI updates first
    router.push(path);
  };

  if (isLoading) {
    return <ContentLoader className="mt-[30%]" />;
  }

  // Failed request or empty payload: isLoading is false but user is still undefined
  if (isError || user == null) {
    const message =
      error instanceof Error ? error.message : 'Could not load your account.';
    return (
      <Container>
        <Toolbar>
          <ToolbarHeading>
            <ToolbarTitle>Account</ToolbarTitle>
          </ToolbarHeading>
          <ToolbarActions />
        </Toolbar>
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-6 text-center text-sm">
          <p className="text-destructive font-medium">{message}</p>
          <button
            type="button"
            className="mt-3 text-primary underline underline-offset-4"
            onClick={() => void refetch()}
          >
            Try again
          </button>
        </div>
      </Container>
    );
  }

  return (
    <AccountProvider user={user}>
      <Container>
        <Toolbar>
          <ToolbarHeading>
            <div className="flex items-center gap-3">
              <Avatar key={user.avatar ?? 'no-avatar'} className="size-12 shrink-0">
                {user.avatar ? (
                  <AvatarImage src={user.avatar} alt={user.name || ''} />
                ) : null}
                <AvatarFallback className="text-lg">
                  {getInitials(user.name || user.email)}
                </AvatarFallback>
              </Avatar>
              <div className="min-w-0 space-y-px">
                <ToolbarTitle className="truncate">{user.name}</ToolbarTitle>
                <div className="truncate text-2sm text-muted-foreground">
                  {user.email}
                  {(() => {
                    const roles = user.roles?.length
                      ? user.roles.map((r: { name: string }) => r.name).join(', ')
                      : (user.role?.name ?? '');
                    return roles ? ` · ${roles}` : '';
                  })()}
                </div>
              </div>
            </div>
          </ToolbarHeading>
          <ToolbarActions />
        </Toolbar>
        <Tabs defaultValue={activeTab} value={activeTab} className="mb-5">
          <TabsList variant="line">
            {Object.entries(navRoutes).map(
              ([key, { title, icon: Icon, path }]) => (
                <TabsTrigger
                  key={key}
                  value={key}
                  disabled={isLoading}
                  onClick={() => handleTabClick(key, path)}
                >
                  <Icon />
                  <span>{title}</span>
                </TabsTrigger>
              ),
            )}
          </TabsList>
        </Tabs>
        <div>{children}</div>
      </Container>
    </AccountProvider>
  );
}
