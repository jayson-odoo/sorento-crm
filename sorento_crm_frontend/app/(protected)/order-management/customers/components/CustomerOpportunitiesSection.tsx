'use client';

import { useState } from 'react';
import { Plus } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { formatCurrency, formatDate } from '@/lib/helpers';
import { useCustomerOpportunities } from '@/app/(protected)/sales/opportunities/hooks/useSalesOpportunities';
import SalesOpportunityModal from '@/app/(protected)/sales/opportunities/components/SalesOpportunityModal';

/**
 * The customer page's Opportunities section (UAC S2-12, plan section 16, J8).
 *
 * "No opportunities yet" with a Log opportunity button preset to this customer; the section
 * renders the same in view and edit (CLAUDE.md CRUD standard) - there is nothing here that
 * changes shape between the two, only whether the surrounding page is editable.
 */
export default function CustomerOpportunitiesSection({
  customerId,
}: {
  customerId: string;
  isEditing?: boolean;
}) {
  const [modalOpen, setModalOpen] = useState(false);
  const { data, isLoading, isError } = useCustomerOpportunities(customerId);
  const opportunities = data ?? [];

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>Opportunities</CardTitle>
        <Button variant="outline" size="sm" onClick={() => setModalOpen(true)}>
          <Plus className="size-4" />
          Log opportunity
        </Button>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-16 w-full" />
        ) : isError ? (
          <p className="text-sm text-destructive">Failed to load opportunities.</p>
        ) : opportunities.length === 0 ? (
          <div className="flex flex-col items-center gap-3 py-6 text-center">
            <span className="text-sm font-medium">No opportunities yet</span>
          </div>
        ) : (
          <ul className="flex flex-col divide-y rounded-lg border">
            {opportunities.map((opp) => (
              <li key={opp.id} className="flex flex-col gap-1 px-3 py-2 sm:flex-row sm:items-center sm:justify-between">
                <a
                  href={`/sales/opportunities/${opp.id}`}
                  className="truncate text-sm font-medium text-primary hover:underline"
                  title={opp.title}
                >
                  {opp.title}
                </a>
                <div className="flex items-center gap-3 text-sm text-muted-foreground">
                  <Badge appearance="light" size="sm">
                    {opp.stage_label}
                  </Badge>
                  <span>{formatCurrency(opp.expected_amount)}</span>
                  <span>{formatDate(opp.expected_close_date)}</span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
      <SalesOpportunityModal
        open={modalOpen}
        onOpenChange={setModalOpen}
        presetCustomerId={customerId}
      />
    </Card>
  );
}
