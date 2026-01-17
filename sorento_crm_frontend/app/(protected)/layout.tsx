'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useSession } from 'next-auth/react';
import { ScreenLoader } from '@/components/common/screen-loader';
import { Demo1Layout } from '../components/layouts/demo1/layout';

export default function ProtectedLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { data: session, status } = useSession();
  const router = useRouter();

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
      router.push('/signin');
    }
  }, [status, router]);

  if (status === 'loading' || status === 'unauthenticated') {
    return <ScreenLoader />;
  }

  if (!session) {
    return <ScreenLoader />;
  }

  return <Demo1Layout>{children}</Demo1Layout>;
}
