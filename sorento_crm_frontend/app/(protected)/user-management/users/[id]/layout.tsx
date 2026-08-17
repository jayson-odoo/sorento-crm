'use client';

import React, { use, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Activity, Mail, MoveLeft, Settings, UserPen } from 'lucide-react';
import { toast } from 'sonner';
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
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Toolbar,
  ToolbarActions,
  ToolbarHeading,
  ToolbarTitle,
} from '@/components/common/toolbar';
import RecordNavigation from '@/components/common/RecordNavigation';
import { useHasPermission } from '@/hooks/usePermissions';
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
  const queryClient = useQueryClient();
  const [resendInvitePending, setResendInvitePending] = useState(false);

  // Use local state to control active tab
  const [activeTab, setActiveTab] = useState<string>('');

  // The logs tab reads GET /system-logs/users/{user_id}, gated on
  // user_management.logs.view - without it the tab is a guaranteed error.
  const canViewLogs = useHasPermission('user_management.logs.view');

  // Define your nav routes
  const navRoutes = useMemo<NavRoutes>(
    () => ({
      general: {
        title: 'Profile',
        icon: UserPen,
        path: `/user-management/users/${id}`,
      },
      ...(canViewLogs
        ? {
            logs: {
              title: 'Activity Logs',
              icon: Activity,
              path: `/user-management/users/${id}/logs`,
            },
          }
        : {}),
    }),
    [id, canViewLogs],
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
      const roles = Array.isArray(data.roles) ? data.roles : [];
      // Transform snake_case from backend to camelCase for frontend
      return {
        ...data,
        roles,
        roleId: roles[0]?.id ?? data.role_id ?? data.roleId,
        respondUserId: data.respond_user_id || data.respondUserId,
        respondSynced: data.respond_synced || data.respondSynced,
        contactNumber: data.contact_number || data.contactNumber,
        respondContactId: data.respond_contact_id ?? data.respondContactId ?? null,
        notifyWhatsapp: data.notify_whatsapp ?? data.notifyWhatsapp ?? false,
        notifyWhatsappSummary: data.notify_whatsapp_summary ?? data.notifyWhatsappSummary ?? false,
        notifyEmailOnAssignment: data.notify_email_on_assignment ?? data.notifyEmailOnAssignment ?? true,
        notifyEmailOnEscalation: data.notify_email_on_escalation ?? data.notifyEmailOnEscalation ?? true,
        notifyWhatsappOnAssignment: data.notify_whatsapp_on_assignment ?? data.notifyWhatsappOnAssignment ?? false,
        notifyWhatsappOnEscalation: data.notify_whatsapp_on_escalation ?? data.notifyWhatsappOnEscalation ?? false,
        notifyEmailOnDeadlineExtended: data.notify_email_on_deadline_extended ?? data.notifyEmailOnDeadlineExtended ?? true,
        notifyWhatsappOnDeadlineExtended: data.notify_whatsapp_on_deadline_extended ?? data.notifyWhatsappOnDeadlineExtended ?? false,
        notifyEmailOnHandling: data.notify_email_on_handling ?? data.notifyEmailOnHandling ?? true,
        notifyWhatsappOnHandling: data.notify_whatsapp_on_handling ?? data.notifyWhatsappOnHandling ?? false,
        notifyEmailOnProductDiscontinued: data.notify_email_on_product_discontinued ?? data.notifyEmailOnProductDiscontinued ?? false,
        notifyWhatsappOnProductDiscontinued: data.notify_whatsapp_on_product_discontinued ?? data.notifyWhatsappOnProductDiscontinued ?? false,
        superiorId: data.superior_id || data.superiorId,
        superiorName: data.superior_name || data.superiorName,
        tier: data.tier != null ? data.tier : undefined,
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

  const handleTabClick = (key: string, path: string) => {
    setActiveTab(key);
    router.push(path);
  };

  const handleResendInvite = async () => {
    setResendInvitePending(true);
    try {
      const res = await apiFetch(`/api/user-management/users/${id}/resend-invite`, {
        method: 'POST',
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        toast.error(data.detail ?? data.message ?? 'Failed to send invitation link.');
        return;
      }
      toast.success(data.message ?? 'Invitation link sent.');
      queryClient.invalidateQueries({ queryKey: ['user-user', id] });
    } catch {
      toast.error('Failed to send invitation link.');
    } finally {
      setResendInvitePending(false);
    }
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
                  <BreadcrumbLink href="/user-management/users">Users</BreadcrumbLink>
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
            {user && (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline" size="icon" disabled={resendInvitePending} aria-label="User options">
                    <Settings className="size-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onClick={handleResendInvite} disabled={resendInvitePending}>
                    <Mail className="size-4" />
                    Send invitation link
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            )}
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
