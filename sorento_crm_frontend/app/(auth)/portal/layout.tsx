import { Suspense, type ReactNode } from 'react';

import SalespersonCrmRedirect from './components/SalespersonCrmRedirect';
import { PortalImpersonationBanner } from './components/PortalImpersonationBanner';

export default function PortalLayout({ children }: { children: ReactNode }) {
  return (
    <>
      <SalespersonCrmRedirect />
      <Suspense fallback={null}>
        <PortalImpersonationBanner />
      </Suspense>
      {children}
    </>
  );
}
