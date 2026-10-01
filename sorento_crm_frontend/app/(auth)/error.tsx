'use client';

import RouteErrorScreen from '@/components/common/RouteErrorScreen';

/**
 * Error boundary for sign-in, sign-up, password reset, portal and the other
 * `(auth)` pages (NEVER-STUCK-UI S5.2, audit row 40). Sign-in is every user's
 * entry point, so a render error there must not be Next's bare "Application
 * error". Next mounts this inside `(auth)/layout.tsx`, so the branded card stays.
 */
export default function AuthError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <RouteErrorScreen
      error={error}
      reset={reset}
      exit={{ href: '/signin', label: 'Back to sign in' }}
    />
  );
}
