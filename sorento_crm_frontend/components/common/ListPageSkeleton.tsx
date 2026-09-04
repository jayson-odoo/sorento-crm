import { Container } from '@/components/common/container';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';

export interface ListPageSkeletonProps {
  /** How many row bars to draw. Ten is a page of a busy list. */
  rows?: number;
  /**
   * Skip the title/toolbar bar and its `Container` - for a `Suspense`
   * boundary wrapped around just the list component on a page that already
   * renders its own `PageHeader` and `Container` above it (M5-02). Without
   * this the fallback would duplicate the title and double the padding.
   */
  bodyOnly?: boolean;
}

/**
 * What a list route shows between the click and the rows (S7-04).
 *
 * The alternative, and what every list did until now, is nothing: the shell
 * stays on the last page until the next one's chunk and data arrive, so a click
 * reads as having missed. A route `loading.tsx` renders INSIDE the layout, so
 * the sidebar, the header and the reader's place in the app all stay put and
 * only the content pane changes - which is the whole point of putting it here
 * rather than behind a full-screen spinner.
 *
 * It is deliberately generic: title, toolbar, header row, rows. A skeleton that
 * tried to match each list's columns would be a second copy of that list's
 * layout, kept in step by hand, to be looked at for a few hundred milliseconds.
 * Generic also because the boundary covers the segment's CHILDREN: a record
 * page under one of these lists is held by the same shape, and a card with
 * bars in it is a fair account of either.
 *
 * Row and header geometry match `data-grid-table.tsx`'s real cells (`px-4
 * py-3 h-[60px]` body, `px-4` header) and the title/crumb block matches
 * `PageHeader.tsx`'s real DOM order - title bar, then the crumb-trail bar
 * below it - so landing on the real page swaps bar-for-content in place
 * rather than shifting the block itself (M5-03).
 */
export function ListPageSkeleton({ rows = 10, bodyOnly = false }: ListPageSkeletonProps) {
  const card = (
    <Card>
      <CardHeader className="flex items-center justify-between gap-3">
        <Skeleton className="h-9 w-64" />
        <div className="flex items-center gap-2">
          <Skeleton className="h-9 w-24" />
          <Skeleton className="h-9 w-9" />
        </div>
      </CardHeader>
      <CardContent className="p-0">
        {/* The header row reads darker than the body rows, as it does in a
            real grid, so the shape is recognisable before the words land. */}
        <div
          data-slot="list-skeleton-header-row"
          className="flex items-center gap-4 border-b border-border px-4 py-3"
        >
          <Skeleton className="h-4 w-4 shrink-0" />
          <Skeleton className="h-3.5 w-32" />
          <Skeleton className="h-3.5 w-24" />
          <Skeleton className="hidden h-3.5 w-28 sm:block" />
          <Skeleton className="hidden h-3.5 w-20 lg:block" />
          <Skeleton className="ms-auto h-3.5 w-16" />
        </div>
        {Array.from({ length: rows }).map((_, index) => (
          <div
            key={index}
            data-slot="list-skeleton-row"
            className="flex h-[60px] items-center gap-4 border-b border-border px-4 py-3 last:border-b-0"
          >
            <Skeleton className="h-4 w-4 shrink-0" />
            <Skeleton className="h-3.5 w-40" />
            <Skeleton className="h-3.5 w-20" />
            <Skeleton className="hidden h-3.5 w-32 sm:block" />
            <Skeleton className="hidden h-3.5 w-16 lg:block" />
            <Skeleton className="ms-auto h-3.5 w-8" />
          </div>
        ))}
      </CardContent>
    </Card>
  );

  if (bodyOnly) return card;

  return (
    <>
      <Container>
        <div className="flex flex-wrap items-center justify-between gap-3 pb-5">
          <div className="space-y-2">
            <Skeleton data-testid="list-skeleton-title" className="h-6 w-56" />
            <Skeleton data-testid="list-skeleton-crumb" className="h-3.5 w-40" />
          </div>
          <Skeleton className="h-9 w-32" />
        </div>
      </Container>

      <Container>{card}</Container>
    </>
  );
}
