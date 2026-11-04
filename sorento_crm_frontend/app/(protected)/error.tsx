'use client';

import { useEffect } from 'react';
import RouteErrorScreen from '@/components/common/RouteErrorScreen';
import { reportClientError } from '@/lib/client-error-report';

/**
 * The route-level error boundary for everything under `app/(protected)`
 * (M5-04). Next mounts a segment's own `error.tsx` INSIDE that segment's
 * `layout.tsx` - it replaces the `children` slot the layout renders, not the
 * layout itself - so `app/(protected)/layout.tsx`'s sidebar and header stay
 * mounted and the reader never loses their place in the app the way a full
 * reload or a blank screen would.
 *
 * `error` and `reset` are Next's own contract for this file; `reset()` tries
 * the failing segment again without a full reload, which only works if
 * whatever threw was transient (a flaky fetch, a race) - a genuine bug
 * throws again, and the link home is the way out of that loop.
 */
export default function ProtectedError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  // One report per error to System Management > Client Errors (CLIENT-ERROR-REPORT).
  useEffect(() => {
    void reportClientError(error, 'protected');
  }, [error]);

  // Fixed copy, never `error.message` (M5-04 review B2): in production a
  // server-component throw yields Next's own developer boilerplate, a client
  // throw yields something like "Cannot read properties of undefined", and a
  // rethrown API error can carry a record id. The shared screen also turns a
  // chunk-load failure (a deploy replaced the build this tab runs) into Reload,
  // since Try again cannot fetch chunks that no longer exist.
  return (
    <RouteErrorScreen
      error={error}
      reset={reset}
      exit={{ href: '/', label: 'Back to dashboards' }}
    />
  );
}
