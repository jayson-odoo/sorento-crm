'use client';

import { ReactNode, useEffect } from 'react';
import { useIsMobile } from '@/hooks/use-mobile';
import { useSettings } from '@/providers/settings-provider';
import { Footer } from './components/footer';
import { Header } from './components/header';
import { Sidebar } from './components/sidebar';
import { ModuleRouteGuard } from '@/app/components/module-route-guard';
import AIAssistantBubble from '@/app/components/common/AIAssistantBubble';
import { ImpersonationBanner } from '@/components/impersonation/ImpersonationBanner';

export function Demo1Layout({ children }: { children: ReactNode }) {
  const isMobile = useIsMobile();
  const { settings, setOption } = useSettings();

  useEffect(() => {
    const bodyClass = document.body.classList;

    if (settings.layouts.demo1.sidebarCollapse) {
      bodyClass.add('sidebar-collapse');
    } else {
      bodyClass.remove('sidebar-collapse');
    }
  }, [settings]); // Runs only on settings update

  useEffect(() => {
    // Set current layout
    setOption('layout', 'demo1');
  }, [setOption]);

  useEffect(() => {
    const bodyClass = document.body.classList;

    // Add a class to the body element
    bodyClass.add('demo1');
    bodyClass.add('sidebar-fixed');
    bodyClass.add('header-fixed');

    const timer = setTimeout(() => {
      bodyClass.add('layout-initialized');
    }, 1000); // 1000 milliseconds

    // Remove the class when the component is unmounted
    return () => {
      bodyClass.remove('demo1');
      bodyClass.remove('sidebar-fixed');
      bodyClass.remove('sidebar-collapse');
      bodyClass.remove('header-fixed');
      bodyClass.remove('layout-initialized');
      clearTimeout(timer);
    };
  }, []); // Runs only once on mount

  return (
    <ModuleRouteGuard>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:start-2 focus:z-(--z-modal) focus:rounded-md focus:bg-background focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:text-foreground focus:shadow-lg focus:outline-none focus:ring-2 focus:ring-ring"
      >
        Skip to main content
      </a>
      <ImpersonationBanner />
      {!isMobile && <Sidebar />}

      {/* min-w-0 lets the content column shrink below its content's intrinsic
          width, so wide children (DataGrids, recharts) scroll/resize within their
          own bounds instead of pushing the whole page wider than the viewport. */}
      <div className="wrapper flex grow flex-col min-w-0">
        <Header />

        <main id="main" className="grow pt-5 min-w-0">
          {children}
        </main>

        <Footer />
      </div>
      <AIAssistantBubble />
    </ModuleRouteGuard>
  );
}

// Export as default for type constraints
export default Demo1Layout;
