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

    // One frame, not a second: this class gates the sidebar/wrapper/header
    // width and padding/inset transitions (see css/demos/demo1.css) so the
    // very first paint - which already reflects a persisted collapsed/
    // expanded setting - does not itself animate. A single rAF is enough for
    // that paint to land before transitions turn on; the earlier 1s delay had
    // no reason to be that long (S8-03 kept this shorter timing, S8's
    // transform-only rewrite of the collapse mechanism was reverted after it
    // distorted both end states - see git history on this file).
    const raf = requestAnimationFrame(() => {
      bodyClass.add('layout-initialized');
    });

    // Remove the class when the component is unmounted
    return () => {
      bodyClass.remove('demo1');
      bodyClass.remove('sidebar-fixed');
      bodyClass.remove('sidebar-collapse');
      bodyClass.remove('header-fixed');
      bodyClass.remove('layout-initialized');
      cancelAnimationFrame(raf);
    };
  }, []); // Runs only once on mount

  return (
    <ModuleRouteGuard>
      <ImpersonationBanner />
      {!isMobile && <Sidebar />}

      {/* min-w-0 lets the content column shrink below its content's intrinsic
          width, so wide children (DataGrids, recharts) scroll/resize within their
          own bounds instead of pushing the whole page wider than the viewport. */}
      <div className="wrapper flex grow flex-col min-w-0">
        <Header />

        <main className="grow pt-5 min-w-0" role="content">
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
