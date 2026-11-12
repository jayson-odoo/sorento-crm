'use client';

import { useEffect } from 'react';
import Link from 'next/link';
import { MoveLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { isChunkLoadError } from '@/lib/chunk-load-error';

// Lives in a dependency-free module so the root boundary can use it too.
export { isChunkLoadError };

export function reloadPage(): void {
  window.location.reload();
}

/**
 * The body of every route group's `error.tsx` (NEVER-STUCK-UI S5): a thrown error
 * ends on this screen, never a blank page or Next's bare "Application error".
 *
 * Copy is fixed, never `error.message` (see `(protected)/error.tsx`): a production
 * render error is developer boilerplate and a rethrown API error can carry a
 * record id. `digest` is the one token that correlates with the server log.
 */
export default function RouteErrorScreen({
  error,
  reset,
  exit,
  onReload = reloadPage,
}: {
  error: Error & { digest?: string };
  reset: () => void;
  /** The way out this route group offers, if any. Customer-facing groups pass none. */
  exit?: { href: string; label: string };
  onReload?: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  const chunk = isChunkLoadError(error);

  return (
    <div className="flex w-full justify-center px-4">
      <Card className="mt-10 w-full max-w-lg">
        <CardHeader>
          <CardTitle>
            {chunk ? 'A new version is available' : 'Something went wrong'}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            {chunk
              ? 'This page could not load because the app was updated. Reload to get the latest version.'
              : 'Something went wrong on this page.'}
          </p>
          {error.digest ? (
            <p className="font-mono text-xs text-muted-foreground">
              Reference: {error.digest}
            </p>
          ) : null}
          <div className="flex flex-wrap items-center gap-2">
            {chunk ? (
              <Button onClick={onReload}>Reload</Button>
            ) : (
              <Button onClick={reset}>Try again</Button>
            )}
            {exit ? (
              <Button asChild variant="outline">
                <Link href={exit.href}>
                  <MoveLeft /> {exit.label}
                </Link>
              </Button>
            ) : null}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
