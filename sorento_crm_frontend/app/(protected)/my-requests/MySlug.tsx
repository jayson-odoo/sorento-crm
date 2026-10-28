'use client';

import type { ReactNode } from 'react';
import { Skeleton } from '@/components/ui/skeleton';
import { useAccountProfileForHeader } from '@/hooks/useAccountProfileForHeader';

/**
 * The CRM-side shell of the portal forms (PORTAL-P3-ROLE-MENU): hands the signed-in salesperson's
 * portal slug (from /users/me) to the same portal components the `/portal/c/{slug}` tree renders.
 */
export function MySlug({ children }: { children: (slug: string) => ReactNode }) {
  const { salesperson } = useAccountProfileForHeader();
  if (!salesperson) return <Skeleton className="h-64 w-full" />;
  return <>{children(salesperson.portalSlug)}</>;
}

// Trim trailing punctuation a link can absorb, as the portal pages do.
export function sanitizeId(raw: string): string {
  return (raw || '').replace(/[^0-9a-fA-F-].*$/, '');
}
