'use client';

import type { ReactNode } from 'react';
import PermissionsLoadBanner from '@/app/components/common/PermissionsLoadBanner';
import PushPrompts from '@/components/pwa/PushPrompts';
import { AppShell } from './shell/AppShell';
import { V2ThemeProvider } from './theme/V2ThemeProvider';
import { useCompanyTheme } from './theme/useCompanyTheme';
import { PreviousVersionChip } from './version/PreviousVersionChip';
import { V2ErrorBoundary } from './version/V2ErrorBoundary';
import { useUiVersion } from './version/useUiVersion';

/**
 * Everything the protected layout renders in UI v2: the company brand + the user's mode, the
 * error boundary with the way back to v1, and the v2 shell. In phase 0 no route has a v2 client
 * yet, so every page is its v1 content inside the v2 shell, marked by the chip (B-10).
 */
export function V2Root({ children }: { children: ReactNode }) {
  const theme = useCompanyTheme();
  const { themeMode } = useUiVersion();
  return (
    <V2ThemeProvider theme={theme} mode={themeMode}>
      <V2ErrorBoundary>
        <AppShell>
          <div className="mb-3 flex justify-end">
            <PreviousVersionChip />
          </div>
          {/* The same in-flow prompts the v1 shell shows above the page. */}
          <PushPrompts />
          <PermissionsLoadBanner />
          {children}
        </AppShell>
      </V2ErrorBoundary>
    </V2ThemeProvider>
  );
}
