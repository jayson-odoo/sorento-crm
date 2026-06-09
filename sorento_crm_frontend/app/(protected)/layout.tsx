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

// #region agent log
useEffect(() => { fetch('http://127.0.0.1:7242/ingest/82ff2983-30f8-41d1-a335-d37b94435673',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'layout.tsx:17',message:'ProtectedLayout auth check',data:{status,hasSession:!!session},timestamp:Date.now(),sessionId:'debug-session',runId:'run1',hypothesisId:'H5'})}).catch(()=>{}); }, [status, session]);
// #endregion

  useEffect(() => {
// #region agent log
fetch('http://127.0.0.1:7242/ingest/82ff2983-30f8-41d1-a335-d37b94435673',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'layout.tsx:21',message:'useEffect exec - checking redirect',data:{status,isUnauthenticated:status==='unauthenticated'},timestamp:Date.now(),sessionId:'debug-session',runId:'run1',hypothesisId:'H5'})}).catch(()=>{});
// #endregion
    if (status === 'unauthenticated') {
// #region agent log
fetch('http://127.0.0.1:7242/ingest/82ff2983-30f8-41d1-a335-d37b94435673',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'layout.tsx:23',message:'Redirecting to signin',data:{status},timestamp:Date.now(),sessionId:'debug-session',runId:'run1',hypothesisId:'H5'})}).catch(()=>{});
// #endregion
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
