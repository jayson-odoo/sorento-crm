'use client';

import React, { use, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { Activity, MoveLeft, UserPen } from 'lucide-react';
import { apiFetch } from '@/lib/api';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';
import { Button } from '@/components/ui/button';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Container } from '@/components/common/container';
import {
  Toolbar,
  ToolbarActions,
  ToolbarHeading,
  ToolbarTitle,
} from '@/components/common/toolbar';
import RecordNavigation from '@/components/common/RecordNavigation';
import { UserProvider } from './components/user-context';
import UserHero from './components/user-hero';

type NavRoutes = Record<
  string,
  {
    title: string;
    icon: React.FC<React.SVGProps<SVGSVGElement>>;
    path: string;
  }
>;

export default function UserLayout({
  params,
  children,
}: {
  params: Promise<{ id: string }>;
  children: React.ReactNode;
}) {
  // 1) Unwrap the params Promise
  const { id } = use(params);
  const pathname = usePathname();
  const router = useRouter();

  // Use local state to control active tab
  const [activeTab, setActiveTab] = useState<string>('');

  // Define your nav routes
  const navRoutes = useMemo<NavRoutes>(
    () => ({
      general: {
        title: 'Profile',
        icon: UserPen,
        path: `/user-management/users/${id}`,
      },
      logs: {
        title: 'Activity Logs',
        icon: Activity,
        path: `/user-management/users/${id}/logs`,
      },
    }),
    [id],
  );

  // Set initial active tab based on the pathname
  useEffect(() => {
    const found = Object.keys(navRoutes).find(
      (key) => pathname === navRoutes[key].path,
    );
    if (found) {
      setActiveTab(found);
    } else {
      setActiveTab('general');
    }
  }, [navRoutes, pathname]);

  const { data: user, isLoading } = useQuery({
    queryKey: ['user-user', id],
    queryFn: async () => {
      const response = await apiFetch(`/api/user-management/users/${id}`);

      if (response.status == 404) {
        router.push('/user-management/users');
      }

      if (!response.ok) {
        const { message } = await response.json();
        throw new Error(message);
      }

      const data = await response.json();
      // Transform snake_case from backend to camelCase for frontend
      return {
        ...data,
        roleId: data.role_id || data.roleId,
        respondUserId: data.respond_user_id || data.respondUserId,
        respondSynced: data.respond_synced || data.respondSynced,
        superiorId: data.superior_id || data.superiorId,
        superiorName: data.superior_name || data.superiorName,
        createdAt: data.created_at || data.createdAt,
        updatedAt: data.updated_at || data.updatedAt,
        lastSignInAt: data.last_sign_in_at || data.lastSignInAt,
        emailVerifiedAt: data.email_verified_at || data.emailVerifiedAt,
        isTrashed: data.is_trashed !== undefined ? data.is_trashed : data.isTrashed,
        invitedByUserId: data.invited_by_user_id || data.invitedByUserId,
        isProtected: data.is_protected !== undefined ? data.is_protected : data.isProtected,
      };
    },
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60, // 60 minutes
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    retry: 1,
  });

  const navigationParams = useMemo(
    () => ({
      pageIndex: 0,
      pageSize: 100,
      sorting: [{ id: 'createdAt', desc: true }],
      searchQuery: '',
      selectedRole: null,
      selectedStatus: null,
    }),
    [],
  );
  const { data: navigationData } = useQuery({
    queryKey: ['user-users-nav', navigationParams],
    queryFn: async () => {
      const sortField = navigationParams.sorting?.[0]?.id || '';
      const sortDirection = navigationParams.sorting?.[0]?.desc ? 'desc' : 'asc';
      const params = new URLSearchParams();
      params.set('page', String(navigationParams.pageIndex + 1));
      params.set('limit', String(navigationParams.pageSize));
      if (sortField) {
        params.set('sort', sortField);
        params.set('dir', sortDirection);
      }
      if (navigationParams.searchQuery) {
        params.set('query', navigationParams.searchQuery);
      }
      if (navigationParams.selectedRole && navigationParams.selectedRole !== 'all') {
        params.set('roleId', navigationParams.selectedRole);
      }
      if (navigationParams.selectedStatus && navigationParams.selectedStatus !== 'all') {
        params.set('status', navigationParams.selectedStatus);
      }

      const response = await apiFetch(`/api/user-management/users?${params.toString()}`);
      if (!response.ok) {
        throw new Error('Failed to fetch users');
      }
      return response.json();
    },
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    retry: 1,
  });
  const navigationItems = navigationData?.data ?? [];

  // Handler for tab click: instantly update active tab then navigate.
  const handleTabClick = (key: string, path: string) => {
    setActiveTab(key);
    // Optionally, you can prefetch or delay navigation slightly if needed
    router.push(path);
  };

  return (
    <UserProvider user={user} isLoading={isLoading}>
      <Container>
        <Toolbar>
          <ToolbarHeading>
            <ToolbarTitle>User</ToolbarTitle>
            <Breadcrumb>
              <BreadcrumbList>
                <BreadcrumbItem>
                  <BreadcrumbLink href="/">Home</BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbPage>User Management</BreadcrumbPage>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbLink href="/user/users">Users</BreadcrumbLink>
                </BreadcrumbItem>
              </BreadcrumbList>
            </Breadcrumb>
          </ToolbarHeading>
          <ToolbarActions>
            <RecordNavigation
              currentId={id}
              items={navigationItems}
              basePath="/user-management/users"
            />
            <Button asChild variant="outline">
              <Link href="/user-management/users">
                <MoveLeft /> Back to users
              </Link>
            </Button>
          </ToolbarActions>
        </Toolbar>
        <UserHero user={user} isLoading={isLoading} />
        <Tabs defaultValue={activeTab} value={activeTab}>
          <TabsList variant="line" className="mb-5">
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
        {children}
      </Container>
    </UserProvider>
  );
}
