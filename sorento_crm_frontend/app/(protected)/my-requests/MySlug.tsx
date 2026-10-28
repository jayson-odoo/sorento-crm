'use client';

import { useEffect, useState, type ReactNode } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { readPortalToken } from '@/app/(auth)/portal/lib/portal-client';
import { portalVerifyPath } from '@/app/(auth)/portal/lib/portal-paths';
import { Skeleton } from '@/components/ui/skeleton';
import { useAccountProfileForHeader } from '@/hooks/useAccountProfileForHeader';

/**
 * The CRM-side shell of the portal forms (PORTAL-P3-ROLE-MENU): hands the signed-in salesperson's
 * portal slug (from /users/me) to the same portal components the `/portal/c/{slug}` tree renders.
 */
export function MySlug({ children }: { children: (slug: string) => ReactNode }) {
  const { salesperson } = useAccountProfileForHeader();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [hasToken, setHasToken] = useState<boolean | null>(null);

  // No portal token on this device: the WhatsApp code once, then back to the page asked for.
  useEffect(() => {
    const token = readPortalToken();
    setHasToken(!!token);
    if (token) return;
    const deep = /^\/my-requests\/([^/]+)\/([^/]+)$/.exec(pathname ?? '');
    router.replace(
      portalVerifyPath({
        type: searchParams?.get('type') ?? deep?.[1],
        id: deep && deep[2] !== 'new' ? deep[2] : null,
      }),
    );
    // Intentional: checked once on arrival.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!salesperson || !hasToken) return <Skeleton className="h-64 w-full" />;
  return <>{children(salesperson.portalSlug)}</>;
}

// Trim trailing punctuation a link can absorb, as the portal pages do.
export function sanitizeId(raw: string): string {
  return (raw || '').replace(/[^0-9a-fA-F-].*$/, '');
}
