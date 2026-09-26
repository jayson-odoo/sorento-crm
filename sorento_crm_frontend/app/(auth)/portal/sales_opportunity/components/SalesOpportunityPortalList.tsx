'use client';

/**
 * Portal Sales Opportunity list - every opportunity this salesperson logged (UAC S2-10).
 *
 * Mobile-first card list, the same shape `PriceTagRequestList` uses: number, title, customer
 * or prospect, stage, amount, close date.
 */
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowLeft, Plus } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { formatCurrency, formatDate } from '@/lib/helpers';
import {
  listPortalSalesOpportunities,
  type PortalSalesOpportunity,
} from '../../lib/sales-opportunity-service';

export function SalesOpportunityPortalList() {
  const router = useRouter();
  const [items, setItems] = useState<PortalSalesOpportunity[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    listPortalSalesOpportunities()
      .then((data) => {
        if (!cancelled) setItems(data);
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
        <Button variant="ghost" size="sm" onClick={() => router.push('/portal')}>
          <ArrowLeft className="mr-1 size-4" /> Back
        </Button>
        <Button size="sm" onClick={() => router.push('/portal/sales_opportunity/new')}>
          <Plus className="mr-1 size-4" /> New
        </Button>
      </div>

      {loading ? (
        <div className="space-y-3">
          <Skeleton className="h-20 w-full rounded-xl" />
          <Skeleton className="h-20 w-full rounded-xl" />
        </div>
      ) : items.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            No sales opportunities yet.
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {items.map((item) => (
            <Card
              key={item.id}
              className="cursor-pointer"
              onClick={() => router.push(`/portal/sales_opportunity/${item.id}`)}
            >
              <CardContent className="flex flex-col gap-1 py-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm font-medium">{item.title}</span>
                  <Badge appearance="light" size="sm">
                    {item.stage_label}
                  </Badge>
                </div>
                <span className="truncate text-xs text-muted-foreground">
                  {item.opportunity_no} &middot; {item.customer_name ?? item.prospect_name ?? '-'}
                </span>
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <span>{formatCurrency(item.expected_amount)}</span>
                  <span>{formatDate(item.expected_close_date)}</span>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
