import Link from 'next/link';
import { MoveLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Container } from '@/components/common/container';

/**
 * The route-level 404 for everything under `app/(protected)` (M5-04) - reached
 * only by a `notFound()` call, or a segment Next has no `page.tsx` for. Same
 * shell survival as `error.tsx`: it renders inside `app/(protected)/layout.tsx`,
 * which keeps the sidebar and header mounted.
 *
 * A scaffold, not yet adopted (M5-04 review S3): as of this commit zero
 * protected pages call `notFound()` - the only callers are the four portal
 * routes under `app/(auth)/portal`. The trigger for adoption is a detail page
 * that today renders inline "X not found" copy switching to call `notFound()`
 * instead of hand-rolling its own empty state; `user-management/contacts/[id]/
 * layout.tsx` (its own inline `<p>Contact not found</p>` branch) is the first
 * candidate. That switch is not made here - this commit only corrects what
 * this file's own comment claimed about it.
 */
export default function ProtectedNotFound() {
  return (
    <Container>
      <Card className="mx-auto mt-10 max-w-lg">
        <CardHeader>
          <CardTitle>Not found</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            This record does not exist or was removed.
          </p>
          <Button asChild variant="outline">
            <Link href="/">
              <MoveLeft /> Back to dashboards
            </Link>
          </Button>
        </CardContent>
      </Card>
    </Container>
  );
}
