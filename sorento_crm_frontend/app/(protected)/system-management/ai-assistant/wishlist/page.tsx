'use client';

import { format } from 'date-fns';
import { useHasPermission } from '@/hooks/usePermissions';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import { SectionSkeleton } from '@/components/common/SectionSkeleton';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { useWishlist } from '../hooks/useAIUsage';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';

const PERMISSION = 'system.ai_assistant_settings.view';

function formatLastSeen(d: string): string {
  try {
    return format(new Date(d), 'MMM d, yyyy HH:mm');
  } catch {
    return d;
  }
}

export default function AIWishlistPage() {
  const hasPermission = useHasPermission(PERMISSION);
  const wishlistQuery = useWishlist(20);

  if (!hasPermission) {
    return (
      <Container>
        <div className="rounded-md border p-6 text-sm text-muted-foreground">
          Forbidden - you don&apos;t have permission to view AI assistant wishlist.
        </div>
      </Container>
    );
  }

  const items = wishlistQuery.data || [];

  return (
    <>
      <Container>
        <PageHeader title="AI Feature Wishlist" />
      </Container>
      <Container className="space-y-4">
        <Card>
          <CardHeader>
            <CardTitle>Clusters</CardTitle>
            <CardDescription>
              Common requests the AI couldn&apos;t fully answer - clustered by similarity.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {wishlistQuery.isLoading ? (
              <SectionSkeleton rows={3} />
            ) : wishlistQuery.isError ? (
              <p className="text-sm text-destructive">
                {(wishlistQuery.error as Error)?.message || 'Failed to load wishlist.'}
              </p>
            ) : items.length === 0 ? (
              <p className="text-sm text-muted-foreground">No unanswered queries yet.</p>
            ) : (
              <ScrollArea>
                <table className="w-auto min-w-full text-sm">
                  <thead>
                    <tr className="border-b text-xs text-muted-foreground">
                      <th className="py-2 text-left font-medium">Representative question</th>
                      <th className="py-2 text-left font-medium">Category</th>
                      <th className="py-2 text-right font-medium">Count</th>
                      <th className="py-2 text-left font-medium">Last seen</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((c) => (
                      <tr key={c.id} className="border-b align-top last:border-0">
                        <td className="py-2 pe-3" title={c.representative_question}>
                          {c.representative_question}
                        </td>
                        <td className="py-2 pe-3">
                          {c.category ? (
                            <Badge variant="secondary" className="text-xs">
                              {c.category}
                            </Badge>
                          ) : (
                            <span className="text-xs text-muted-foreground"> - </span>
                          )}
                        </td>
                        <td className="py-2 pe-3 text-right tabular-nums">{c.count}</td>
                        <td className="py-2 text-xs text-muted-foreground">
                          {formatLastSeen(c.last_seen_at)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <ScrollBar orientation="horizontal" />
              </ScrollArea>
            )}
          </CardContent>
        </Card>
      </Container>
    </>
  );
}
