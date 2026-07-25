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
import { CompanyProvider } from '@/app/providers/CompanyProvider';

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
      // Permanent deep-link-after-login: capture the FULL relative URL the user
      // landed on (path + query + hash), not just the pathname, so any internal
      // link survives the sign-in round-trip. The signin page reads callbackUrl
      // and only honours same-origin relative paths (starts with '/', not '//').
      // This is staff/NextAuth only — the portal contact OTP flow uses public
      // /view links + confirm-identity and never hits this protected layout.
      const loc = typeof window !== 'undefined' ? window.location : null;
      const target = loc
        ? `${loc.pathname}${loc.search}${loc.hash}`
        : pathname ?? '';
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
    <CompanyProvider>
      <UploadManagerProvider>
        <MyDownloadsProvider>
          <GuideTargetSpotlight />
          <Demo1Layout>{children}</Demo1Layout>
          <UploadActivityDrawer />
          <MyDownloadsDrawer />
        </MyDownloadsProvider>
      </UploadManagerProvider>
    </CompanyProvider>
  );
}
