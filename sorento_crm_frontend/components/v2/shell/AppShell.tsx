'use client';

import { useState, type ReactNode } from 'react';
import { ModuleRouteGuard } from '@/app/components/module-route-guard';
import AIAssistantBubble from '@/app/components/common/AIAssistantBubble';
import { MobileNavSheet } from './MobileNavSheet';
import { PrimaryActionHost } from './PrimaryActionContext';
import { Sidebar } from './Sidebar';
import { SystemBanner } from './SystemBanner';
import { Topbar } from './Topbar';
import { usePageView } from './usePageView';
import { useIsPhone } from './useViewport';

/**
 * The UI v2 application shell (E-1): banner above the top bar, the sidebar on desktop, the
 * navigation drawer on a phone, and the page inside one <main>. It is the only place page-view
 * telemetry is mounted (D-5) and the only host of the floating primary action (R16).
 */
export function AppShell({ children }: { children: ReactNode }) {
  usePageView();
  const isPhone = useIsPhone();
  const [navOpen, setNavOpen] = useState(false);

  return (
    <ModuleRouteGuard>
      <PrimaryActionHost>
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:fixed focus:start-2 focus:top-2 focus:z-(--z-modal) focus:rounded-md focus:bg-background focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:text-foreground focus:shadow-lg focus:ring-2 focus:ring-ring"
        >
          Skip to main content
        </a>
        <SystemBanner />
        {!isPhone && <Sidebar />}
        <div className={isPhone ? 'flex min-h-dvh min-w-0 flex-col' : 'flex min-h-dvh min-w-0 flex-col ps-(--v2-sidebar-width)'}>
          <Topbar onOpenNav={() => setNavOpen(true)} />
          <main
            id="main"
            tabIndex={-1}
            className="min-w-0 grow px-4 pt-5 pb-[calc(1.25rem+var(--floating-action-room,0px))] focus:outline-none lg:px-6"
          >
            {children}
          </main>
        </div>
        {isPhone && <MobileNavSheet open={navOpen} onOpenChange={setNavOpen} />}
        <AIAssistantBubble />
      </PrimaryActionHost>
    </ModuleRouteGuard>
  );
}
