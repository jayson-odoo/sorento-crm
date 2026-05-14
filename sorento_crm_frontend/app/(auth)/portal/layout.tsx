import { Suspense, type ReactNode } from 'react';

import { PortalImpersonationBanner } from './components/PortalImpersonationBanner';

export default function PortalLayout({ children }: { children: ReactNode }) {
  return (
    <>
      <Suspense fallback={null}>
        <PortalImpersonationBanner />
      </Suspense>
      {children}
    </>
  );
}
