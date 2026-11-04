'use client';

import { ReactNode } from 'react';
import dynamic from 'next/dynamic';
import { LayoutLoadingFallback } from '@/components/LayoutLoadingFallback';
import { ComponentStackBoundary } from '@/components/common/ComponentStackBoundary';

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
  // Tags whatever escapes to app/global-error.tsx with the component stack, so a crash
  // report names the component even when the error has no stack (Safari DOMException).
  return (
    <ComponentStackBoundary>
      <ClientProviders>{children}</ClientProviders>
    </ComponentStackBoundary>
  );
}
