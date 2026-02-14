'use client';

import { ReactNode } from 'react';
import { QueryProvider } from '@/providers/query-provider';
import { AuthProvider } from '@/providers/auth-provider';
import { SettingsProvider } from '@/providers/settings-provider';
import { ThemeProvider } from '@/providers/theme-provider';
import { I18nProvider } from '@/providers/i18n-provider';
import { TooltipsProvider } from '@/providers/tooltips-provider';
import { ModulesProvider } from '@/providers/modules-provider';
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
              <TooltipsProvider>
                <ModulesProvider>
                  {children}
                  <Toaster />
                </ModulesProvider>
              </TooltipsProvider>
            </I18nProvider>
          </ThemeProvider>
        </SettingsProvider>
      </AuthProvider>
    </QueryProvider>
  );
}
