'use client';

import { useEffect } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { useSession } from 'next-auth/react';
import { ScreenLoader } from '@/components/common/screen-loader';
import { Demo1Layout } from '../components/layouts/demo1/layout';
import { useImpersonation } from '@/hooks/useImpersonation';
import GuideTargetSpotlight from '@/app/components/common/GuideTargetSpotlight';
import {
  UploadActivityDrawer,
  UploadManagerProvider,
} from '@/components/upload-activity';
import { MyDownloadsProvider } from '@/components/my-downloads/MyDownloadsContext';
import { MyDownloadsDrawer } from '@/components/my-downloads/MyDownloadsDrawer';

export default function ProtectedLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { data: session, status } = useSession();
  const router = useRouter();
  const pathname = usePathname();
  const { hydrate } = useImpersonation();

  useEffect(() => {
    if (status === 'authenticated') {
      hydrate().catch(() => {});
    }
  }, [status, hydrate]);

  useEffect(() => {
    if (status === 'unauthenticated') {
      const hashFragment = typeof window !== 'undefined' ? window.location.hash : '';
      const target = pathname ? `${pathname}${hashFragment}` : '';
      const callbackUrl = target ? `/signin?callbackUrl=${encodeURIComponent(target)}` : '/signin';
      router.push(callbackUrl);
    }
  }, [status, router, pathname]);

  if (status === 'loading' || status === 'unauthenticated') {
    return <ScreenLoader />;
  }

  if (!session) {
    return <ScreenLoader />;
  }

  return (
    <UploadManagerProvider>
      <MyDownloadsProvider>
        <GuideTargetSpotlight />
        <Demo1Layout>{children}</Demo1Layout>
        <UploadActivityDrawer />
        <MyDownloadsDrawer />
      </MyDownloadsProvider>
    </UploadManagerProvider>
  );
}
