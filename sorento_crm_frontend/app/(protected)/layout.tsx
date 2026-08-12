'use client';

import { useEffect } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { useSession, getSession } from 'next-auth/react';
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
    // Never log out on a transient `unauthenticated`. A full page reload (e.g. a
    // plain-anchor link), a fast refresh, or a slow/aborted `/api/auth/session`
    // can momentarily report no session even though the cookie is valid. Before
    // redirecting to /signin we wait briefly AND re-verify with a forced
    // getSession(); only a confirmed null session redirects. A real sign-out
    // still kicks the user out (the re-check also returns null).
    if (status !== 'unauthenticated') return;
    let cancelled = false;
    const timer = setTimeout(async () => {
      try {
        const fresh = await getSession();
        if (fresh) return; // transient null recovered — stay put
      } catch {
        // fall through to redirect on a hard failure
      }
      if (cancelled) return;
      const hashFragment = typeof window !== 'undefined' ? window.location.hash : '';
      const target = pathname ? `${pathname}${hashFragment}` : '';
      const callbackUrl = target ? `/signin?callbackUrl=${encodeURIComponent(target)}` : '/signin';
      router.push(callbackUrl);
    }, 800);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
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
