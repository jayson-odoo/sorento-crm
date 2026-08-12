'use client';

import { ReactNode } from 'react';
import type { Session } from 'next-auth';
import dynamic from 'next/dynamic';
import { LayoutLoadingFallback } from '@/components/LayoutLoadingFallback';

const ClientProviders = dynamic(
  () =>
    import('@/components/ClientProviders').then((mod) => ({
      default: mod.ClientProviders,
    })),
  {
    ssr: false,
    loading: () => <LayoutLoadingFallback />,
  },
);

export function DynamicClientProviders({
  children,
  session,
}: {
  children: ReactNode;
  session?: Session | null;
}) {
  return <ClientProviders session={session}>{children}</ClientProviders>;
}
