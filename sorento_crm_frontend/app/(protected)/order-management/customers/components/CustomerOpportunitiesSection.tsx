'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Plus } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { formatCurrency, formatDate } from '@/lib/helpers';
import { useHasPermission } from '@/hooks/usePermissions';
import { useTenantModules } from '@/hooks/useTenantModules';
import { useCustomerOpportunities } from '@/app/(protected)/sales/opportunities/hooks/useSalesOpportunities';
import SalesOpportunityModal from '@/app/(protected)/sales/opportunities/components/SalesOpportunityModal';

/**
 * The customer page's Opportunities section (UAC S2-12, plan section 16, J8).
 *
 * "No opportunities yet" with a Log opportunity button preset to this customer; the section
 * renders the same in view and edit (CLAUDE.md CRUD standard) - there is nothing here that
 * changes shape between the two, only whether the surrounding page is editable.
 *
 * Gated (Phase 3 fix B4): this section lives on the Customer page, which belongs to the
 * `order_management` module, not `sales` - nothing else on this page hides it when `sales`
 * is off or the viewer has no `sales.opportunities.view`. Fails OPEN while the module list is
 * still loading (the same rule `PromotionsList` uses), so it does not flash hidden-then-shown.
 */
export default function CustomerOpportunitiesSection({
  customerId,
}: {
  customerId: string;
  isEditing?: boolean;
}) {
  const [modalOpen, setModalOpen] = useState(false);
  const { enabledModuleKeys, isLoading: modulesLoading } = useTenantModules();
  const salesModuleEnabled =
    modulesLoading || enabledModuleKeys == null || enabledModuleKeys.has('sales');
  const canView = useHasPermission('sales.opportunities.view');
  const canAdd = useHasPermission('sales.opportunities.add');
  const { data, isLoading, isError } = useCustomerOpportunities(canView ? customerId : null);
  const opportunities = data ?? [];

  if (!salesModuleEnabled || !canView) return null;

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>Opportunities</CardTitle>
        {canAdd ? (
          <Button variant="outline" size="sm" onClick={() => setModalOpen(true)}>
            <Plus className="size-4" />
            Log opportunity
          </Button>
        ) : null}
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-16 w-full" />
        ) : isError ? (
          <p className="text-sm text-destructive">Failed to load opportunities.</p>
        ) : opportunities.length === 0 ? (
          <div className="flex flex-col items-center gap-3 py-6 text-center">
            <span className="text-sm font-medium">No opportunities yet</span>
            {canAdd ? (
              <Button variant="outline" size="sm" onClick={() => setModalOpen(true)}>
                <Plus className="size-4" />
                Log opportunity
              </Button>
            ) : null}
          </div>
        ) : (
          <ul className="flex flex-col divide-y rounded-lg border">
            {opportunities.map((opp) => (
              <li key={opp.id} className="flex flex-col gap-1 px-3 py-2 sm:flex-row sm:items-center sm:justify-between">
                <Link
                  href={`/sales/opportunities/${opp.id}`}
                  className="truncate text-sm font-medium text-primary hover:underline"
                  title={opp.title}
                >
                  {opp.title}
                </Link>
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
      {canAdd ? (
        <SalesOpportunityModal
          open={modalOpen}
          onOpenChange={setModalOpen}
          presetCustomerId={customerId}
        />
      ) : null}
    </Card>
  );
}
