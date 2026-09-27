'use client';

import { Fragment, useEffect } from 'react';
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
import PushPrompts from '@/components/pwa/PushPrompts';

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
      // This is staff/NextAuth only - the portal contact OTP flow uses public
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
          <Demo1Layout>
            {/* In flow at the top of the page body: neither prompt can cover the
                primary action of the page beneath it (AC-P16). Keyed because
                Demo1Layout renders its children as a list inside <main>, and the
                routed page arrives with no key of its own: without these, every
                page logged a missing-key error (the dev "1 Issue" badge, #1286). */}
            <PushPrompts key="push-prompts" />
            <Fragment key="page">{children}</Fragment>
          </Demo1Layout>
          <UploadActivityDrawer />
          <MyDownloadsDrawer />
        </MyDownloadsProvider>
      </UploadManagerProvider>
    </CompanyProvider>
  );
}
