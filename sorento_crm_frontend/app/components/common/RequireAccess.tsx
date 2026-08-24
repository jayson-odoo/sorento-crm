'use client';

import type { ReactNode } from 'react';
import { useSession } from 'next-auth/react';
import { ScreenLoader } from '@/components/common/screen-loader';
import { isSuperadminUser } from '@/lib/is-superadmin';
import { usePermissions } from '@/hooks/usePermissions';
import AccessDenied from '@/app/components/common/AccessDenied';

type RequireAccessProps = {
  children: ReactNode;
} & (
  | { superadmin: true; permission?: never }
  | { permission: string; superadmin?: never }
);

/**
 * Page-level access guard. Renders <AccessDenied/> (NOT a redirect) when the
 * current user is denied, a loader while access is still resolving, else the
 * page body. Mirrors the sidebar's fail-open-while-loading behaviour so the
 * denied state never flashes before permissions resolve.
 *
 * Two modes:
 *  - <RequireAccess superadmin> - allowed only for superadmin/admin roles.
 *  - <RequireAccess permission="slug"> - allowed only when the user's
 *    permission set includes `slug`.
 */
export default function RequireAccess(props: RequireAccessProps) {
  if (props.superadmin) {
    return <SuperadminGate>{props.children}</SuperadminGate>;
  }
  return <PermissionGate permission={props.permission}>{props.children}</PermissionGate>;
}

function SuperadminGate({ children }: { children: ReactNode }) {
  const { data: session, status } = useSession();
  if (status === 'loading') return <ScreenLoader />;
  if (!isSuperadminUser(session?.user)) return <AccessDenied />;
  return <>{children}</>;
}

function PermissionGate({
  permission,
  children,
}: {
  permission: string;
  children: ReactNode;
}) {
  const { permissionSet, isLoading } = usePermissions();
  if (isLoading) return <ScreenLoader />;
  if (!permissionSet.has(permission)) return <AccessDenied />;
  return <>{children}</>;
}
