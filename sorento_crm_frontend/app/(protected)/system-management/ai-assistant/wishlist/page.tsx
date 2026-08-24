'use client';

import { format } from 'date-fns';
import { Loader2 } from 'lucide-react';
import { useHasPermission } from '@/hooks/usePermissions';
import { Container } from '@/components/common/container';
import { Toolbar, ToolbarHeading, ToolbarTitle } from '@/components/common/toolbar';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { useWishlist } from '../hooks/useAIUsage';

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
        <Toolbar>
          <ToolbarHeading>
            <ToolbarTitle>AI Feature Wishlist</ToolbarTitle>
            <Breadcrumb>
              <BreadcrumbList>
                <BreadcrumbItem>
                  <BreadcrumbLink href="/">Home</BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbLink href="/system-management/ai-assistant">AI Assistant</BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbPage>Wishlist</BreadcrumbPage>
                </BreadcrumbItem>
              </BreadcrumbList>
            </Breadcrumb>
          </ToolbarHeading>
        </Toolbar>
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
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" />
                Loading...
              </div>
            ) : wishlistQuery.isError ? (
              <p className="text-sm text-destructive">
                {(wishlistQuery.error as Error)?.message || 'Failed to load wishlist.'}
              </p>
            ) : items.length === 0 ? (
              <p className="text-sm text-muted-foreground">No unanswered queries yet.</p>
            ) : (
              <table className="w-full text-sm">
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
            )}
          </CardContent>
        </Card>
      </Container>
    </>
  );
}
