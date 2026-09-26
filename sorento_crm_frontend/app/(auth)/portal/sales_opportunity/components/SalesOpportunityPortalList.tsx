'use client';

/**
 * Portal Sales Opportunity list (UAC S2-10; plan section 16).
 *
 * Mobile-first card list, the same shape `PriceTagRequestList` uses: number, title, customer
 * or prospect, stage, amount, close date. Navigation is plain `<Link>`s, never `useRouter` -
 * this component is unit-tested without a Next.js router context.
 */
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { ArrowLeft, Plus } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import {
  listPortalSalesOpportunities,
  type PortalSalesOpportunity,
} from '../../lib/sales-opportunity-service';

export default function SalesOpportunityPortalList() {
  const [items, setItems] = useState<PortalSalesOpportunity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setError(false);
    listPortalSalesOpportunities()
      .then((data) => {
        if (!cancelled) setItems(data);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="mx-auto w-full max-w-2xl space-y-4 px-3 pb-8 pt-4">
      <div className="flex items-center justify-between">
        <Button variant="ghost" size="sm" asChild>
          <Link href="/portal">
            <ArrowLeft className="mr-1 size-4" /> Back
          </Link>
        </Button>
        <Button size="sm" asChild>
          <Link href="/portal/sales_opportunity/new">
            <Plus className="mr-1 size-4" /> New
          </Link>
        </Button>
      </div>

      {loading ? (
        <div className="space-y-3">
          <Skeleton className="h-20 w-full rounded-xl" />
          <Skeleton className="h-20 w-full rounded-xl" />
        </div>
      ) : error ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-destructive">
            Failed to load opportunities.
          </CardContent>
        </Card>
      ) : items.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            No opportunities yet.
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {items.map((item) => (
            // aria-label replaces the default (every visible field concatenated, including
            // the stage Badge's own text) with a short name: a card whose stage happens to be
            // "New" would otherwise give this row's link an accessible name containing "New",
            // colliding with the New-opportunity link above under a role+name query.
            <Link
              key={item.id}
              href={`/portal/sales_opportunity/${item.id}`}
              className="block"
              aria-label={`Open ${item.opportunity_no}`}
            >
              <Card className="cursor-pointer">
                <CardContent className="flex flex-col gap-1 py-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-sm font-medium">{item.title}</span>
                    <Badge appearance="light" size="sm">
                      {item.stage_label}
                    </Badge>
                  </div>
                  <span className="truncate text-xs text-muted-foreground">
                    <span>{item.opportunity_no}</span> &middot;{' '}
                    <span>{item.customer_name ?? item.prospect_name ?? '-'}</span>
                  </span>
                  <div className="flex items-center justify-between text-xs text-muted-foreground">
                    <span>RM {item.expected_amount}</span>
                    <span>{item.expected_close_date}</span>
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
