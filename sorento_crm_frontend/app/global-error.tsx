'use client';

import { useEffect, useState } from 'react';
import GlobalErrorView from '@/components/common/GlobalErrorView';
import { claimStaleChunkReload, isChunkLoadError } from '@/lib/chunk-load-error';
import { reportClientError } from '@/lib/client-error-report';

/**
 * Catches what escapes the root layout (NEVER-STUCK-UI S5.1, audit row 33): above
 * all a failed `ssr:false` chunk load of the client providers
 * (`components/DynamicClientProviders.tsx`) when a deploy has replaced the build
 * the tab is running. Without this file that is a blank page. It replaces the root
 * layout, so it renders its own `<html>` and `<body>`, and imports nothing that
 * shares a chunk with the UI it is standing in for.
 *
 * CLIENT-ERROR-REPORT: a chunk load error reloads the page once by itself (guarded
 * per build in sessionStorage, so it can never loop), and the screen shows only when
 * that reload did not fix it. Whenever the screen shows, one report goes to the
 * backend so the cause is visible under System Management > Client Errors.
 */
// Set once the reload is issued. StrictMode runs the effect twice in dev; without
// this the second run would find the reload already claimed and show the screen
// (and file a report) while the page is in the middle of reloading.
let reloadIssued = false;

export default function GlobalError({
  error,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  // A chunk error starts hidden: the effect either reloads (and the screen never
  // flashes) or reveals it. Derived from `error` alone, so server and client agree.
  const [showScreen, setShowScreen] = useState(() => !isChunkLoadError(error));

  useEffect(() => {
    console.error(error);
    if (reloadIssued) return;
    if (isChunkLoadError(error) && claimStaleChunkReload()) {
      reloadIssued = true;
      window.location.reload();
      return;
    }
    setShowScreen(true);
    void reportClientError(error, 'global');
  }, [error]);

  return (
    <html lang="en">
      <body style={{ margin: 0 }}>
        {showScreen ? (
          <GlobalErrorView
            digest={error.digest}
            onReload={() => window.location.reload()}
          />
        ) : null}
      </body>
    </html>
  );
}
