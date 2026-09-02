'use client';

import { ReactNode } from 'react';
import { QueryProvider } from '@/providers/query-provider';
import { AuthProvider } from '@/providers/auth-provider';
import { SettingsProvider } from '@/providers/settings-provider';
import { ThemeProvider } from '@/providers/theme-provider';
import { I18nProvider } from '@/providers/i18n-provider';
import { ModulesProvider } from '@/providers/modules-provider';
import { TooltipProvider } from '@/components/ui/tooltip';
import { Toaster } from '@/components/ui/sonner';

/**
 * Single client bundle that wraps all app providers.
 * Loaded via next/dynamic from the root layout to keep the layout chunk smaller
 * and avoid ChunkLoadError timeouts on slow connections.
 */
export function ClientProviders({ children }: { children: ReactNode }) {
  return (
    <QueryProvider>
      <AuthProvider>
        <SettingsProvider>
          <ThemeProvider>
            <I18nProvider>
              {/* The ONE TooltipProvider for the whole app (M2-07) - a second
                  one anywhere below this shadows the shared 700ms-first/
                  300ms-sibling rhythm for its own subtree. */}
              <TooltipProvider delayDuration={700} skipDelayDuration={300}>
                <ModulesProvider>
                  {children}
                  <Toaster />
                </ModulesProvider>
              </TooltipProvider>
            </I18nProvider>
          </ThemeProvider>
        </SettingsProvider>
      </AuthProvider>
    </QueryProvider>
  );
}
