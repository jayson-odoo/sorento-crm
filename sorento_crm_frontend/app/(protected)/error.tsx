'use client';

import { useEffect } from 'react';
import Link from 'next/link';
import { MoveLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Container } from '@/components/common/container';

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
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <Container>
      <Card className="mx-auto mt-10 max-w-lg">
        <CardHeader>
          <CardTitle>Something went wrong</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">{error.message}</p>
          <div className="flex flex-wrap items-center gap-2">
            <Button onClick={reset}>Try again</Button>
            <Button asChild variant="outline">
              <Link href="/">
                <MoveLeft /> Back to dashboards
              </Link>
            </Button>
          </div>
        </CardContent>
      </Card>
    </Container>
  );
}
