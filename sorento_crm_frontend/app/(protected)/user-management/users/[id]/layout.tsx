'use client';

import React, { use, useEffect, useMemo, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { Activity, UserPen } from 'lucide-react';
import { apiFetch } from '@/lib/api';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import BackToList from '@/components/common/BackToList';
import { useHasPermission } from '@/hooks/usePermissions';
import { useDeletedRecordGuard } from '@/hooks/useDeletedRecordGuard';
import { getContact } from '../../contacts/[id]/services/contactService';
import { UserProvider } from './components/user-context';
import UserHero from './components/user-hero';

// PHASE 1 MOCK: swap in Phase 2 once `GET /users/{id}` answers the S3 contract's
// 1.7 fields itself. `linkedContact` and `phoneDiffersFromContact` are computed
// below from fields the backend already sends (`respond_contact_id`,
// `contact_number`) - only `phoneVerifiedAt`, `lastSignInMethod` and
// `needsInvitation` are guesses this constant marks, since nothing on the user
// today carries verification, session-method or invite history.
const S3_USE_MOCKS = true;

/** Digits only, so a `+60`, a leading `0` or spacing never reads as "differs"
 *  on their own. An approximation for Phase 1 - Phase 2's flag is the server's
 *  own `normalize_msisdn` compare (S3 contract 1.7). */
function digitsOnly(phone: string | null | undefined): string {
  return (phone ?? '').replace(/\D/g, '');
}

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
      const respondContactId = data.respond_contact_id ?? data.respondContactId ?? null;

      // Real, not mocked: the contact is already fetchable, and comparing its
      // phone to the user's own needs nothing the backend hasn't sent already.
      let linkedContact: { id: string; name: string | null; phone_number: string | null } | null =
        null;
      let phoneDiffersFromContact = false;
      if (respondContactId) {
        try {
          const contact = await getContact(respondContactId);
          linkedContact = {
            id: contact.id,
            name: contact.name ?? null,
            phone_number: contact.phone_number ?? null,
          };
          phoneDiffersFromContact =
            digitsOnly(data.contact_number) !== digitsOnly(contact.phone_number);
        } catch {
          // The contact fetch is a nicety for the Sign-in section, never a
          // reason to fail loading the user itself.
        }
      }

      // Transform snake_case from backend to camelCase for frontend
      return {
        ...data,
        phoneVerifiedAt: data.phone_verified_at ?? data.phoneVerifiedAt ?? null,
        linkedContact: data.linked_contact ?? data.linkedContact ?? linkedContact,
        phoneDiffersFromContact:
          data.phone_differs_from_contact ?? data.phoneDiffersFromContact ?? phoneDiffersFromContact,
        lastSignInMethod: data.last_sign_in_method ?? data.lastSignInMethod ?? null,
        needsInvitation:
          data.needs_invitation ??
          data.needsInvitation ??
          (S3_USE_MOCKS ? Boolean(data.email) && !data.password : false),
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
        notifyEmailOnMention: data.notify_email_on_mention ?? data.notifyEmailOnMention ?? true,
        notifyEmailOnProductDiscontinued: data.notify_email_on_product_discontinued ?? data.notifyEmailOnProductDiscontinued ?? false,
        notifyWhatsappOnProductDiscontinued: data.notify_whatsapp_on_product_discontinued ?? data.notifyWhatsappOnProductDiscontinued ?? false,
        productDiscontinuedScopes: data.product_discontinued_scopes ?? data.productDiscontinuedScopes ?? [],
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
    refetchOnReconnect: false,
    retry: 1,
  });

  // A user this tab deleted a moment ago is gone on purpose, so a stale link to
  // them returns to the list quietly instead of reading as a fault (S6 feedback C).
  useDeletedRecordGuard({
    entityId: id,
    notFound: !isLoading && !user,
    listPath: '/user-management/users',
  });

  const handleTabClick = (key: string, path: string) => {
    setActiveTab(key);
    router.push(path);
  };

  return (
    <UserProvider user={user} isLoading={isLoading}>
      <Container>
        <PageHeader
          title="User"
          actions={
            <BackToList listPath="/user-management/users" label="Back to users" />
          }
        />
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
