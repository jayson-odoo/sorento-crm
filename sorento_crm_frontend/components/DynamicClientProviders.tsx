'use client';

import { ReactNode } from 'react';
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

export function DynamicClientProviders({ children }: { children: ReactNode }) {
  return <ClientProviders>{children}</ClientProviders>;
}
