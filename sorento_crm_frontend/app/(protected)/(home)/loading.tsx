import { Container } from '@/components/common/container';
import { SectionSkeleton } from '@/components/common/SectionSkeleton';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';

/**
 * The dashboard's shape while its chunk and widgets arrive, so the first frame
 * after sign-in is the shell plus this rather than the sign-in card sitting
 * still (fix round 4, #1307). Scoped to the `(home)` group on purpose: a
 * `loading.tsx` at `(protected)` would become the fallback for every segment
 * below it that has none of its own.
 */
export default function Loading() {
  return (
    <Container width="fluid">
      <div className="space-y-2 pb-5" data-slot="home-skeleton-header">
        <Skeleton className="h-7 w-40" />
        <Skeleton className="h-3.5 w-24" />
      </div>
      <Card className="mb-5">
        <CardHeader>
          <Skeleton className="h-9 w-64" />
        </CardHeader>
        <CardContent>
          <SectionSkeleton rows={4} />
        </CardContent>
      </Card>
      <Card>
        <CardContent className="pt-5">
          <SectionSkeleton rows={3} />
        </CardContent>
      </Card>
    </Container>
  );
}
