'use client';

import { useEffect, useState } from 'react';
import { LoaderCircleIcon } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { RecordNavigation } from '@/components/common/RecordNavigation';
import { SearchableSelect, type SearchableSelectOption } from '@/components/common/SearchableSelect';
import { formatCurrency, formatDate, formatDateTimeInMalaysia } from '@/lib/helpers';
import { getSalesOpportunitySalesOrderOptions } from '../../services/salesOpportunityService';
import {
  useSalesOpportunity,
  useSalesOpportunityMeta,
  useSaveSalesOpportunity,
} from '../../hooks/useSalesOpportunities';
import type { SalesOpportunityTransition } from '../../types/salesOpportunity.types';

/**
 * `/sales/opportunities/{id}` detail page (UAC S2-11, S2-12, S2-13; plan section 16).
 *
 * View and edit are the same layout (CLAUDE.md CRUD standard): stage buttons come only from
 * `available_transitions`, never guessed at; Lost requires a reason from the lookup, Won
 * offers an optional sales order limited to the customer. Every section - Opportunity,
 * Products, Stage - renders with an empty state.
 */
export default function SalesOpportunityDetail({ id }: { id: string }) {
  const { data: opportunity, isLoading, isError } = useSalesOpportunity(id);
  const { data: meta } = useSalesOpportunityMeta();
  const save = useSaveSalesOpportunity();

  const [pending, setPending] = useState<SalesOpportunityTransition | null>(null);
  const [lostReason, setLostReason] = useState('');
  const [salesOrderId, setSalesOrderId] = useState('');

  useEffect(() => {
    setPending(null);
    setLostReason('');
    setSalesOrderId('');
  }, [id]);

  const lostReasonOptions: SearchableSelectOption[] = (meta?.lost_reasons ?? []).map((r) => ({
    value: r.value,
    label: r.label,
  }));

  // Reviewer should-fix 3: a live search over every sales order, not a fetch-once list -
  // the same reasoning every other id picker in this app follows for a catalog that can
  // outgrow one page (LESSONS 70).
  const fetchSalesOrderOptions = async (q: string): Promise<SearchableSelectOption[]> => {
    const rows = await getSalesOpportunitySalesOrderOptions(id, q);
    return rows.map((r) => ({
      value: r.id,
      label: r.customer_name ? `${r.so_number} - ${r.customer_name}` : r.so_number,
    }));
  };

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-24 w-full rounded-xl" />
        <Skeleton className="h-48 w-full rounded-xl" />
      </div>
    );
  }

  if (isError || !opportunity) {
    return (
      <Card className="flex flex-col items-center gap-3 p-10 text-center">
        <div className="text-sm font-semibold">Sales opportunity not found</div>
        <p className="max-w-md text-sm text-muted-foreground">
          This opportunity does not exist, or it was deleted after this link was made.
        </p>
      </Card>
    );
  }

  const customerLabel = opportunity.customer_name ?? opportunity.prospect_name ?? 'No customer yet';
  const lines = opportunity.lines ?? [];
  const transitions = opportunity.available_transitions ?? [];

  const confirmMove = async () => {
    if (!pending) return;
    if (pending.key === 'lost' && !lostReason) return;
    try {
      await save.mutateAsync({
        id,
        status_id: pending.to_status_id,
        ...(pending.key === 'lost' ? { lost_reason: lostReason } : {}),
        ...(pending.key === 'won' && salesOrderId ? { sales_order_id: salesOrderId } : {}),
      });
      setPending(null);
      setLostReason('');
      setSalesOrderId('');
    } catch {
      // The hook toasted the reason; stay on the pending move so nothing typed is lost.
    }
  };

  return (
    <div className="space-y-4">
      <Card className="flex flex-col gap-2 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex min-w-0 flex-wrap items-center gap-3">
            <h2 className="truncate text-lg font-semibold" title={opportunity.title}>
              {opportunity.title}
            </h2>
            <Badge appearance="light">{opportunity.stage_label}</Badge>
          </div>
          <RecordNavigation
            index={null}
            total={0}
            hasPrevious={false}
            hasNext={false}
            onPrevious={() => {}}
            onNext={() => {}}
            ariaLabel="record navigation"
          />
        </div>
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
          <span>{opportunity.opportunity_no}</span>
          {opportunity.created_at ? (
            <span>Created {formatDateTimeInMalaysia(opportunity.created_at)}</span>
          ) : null}
          {opportunity.updated_at ? (
            <span>Updated {formatDateTimeInMalaysia(opportunity.updated_at)}</span>
          ) : null}
        </div>
      </Card>

      <Card>
        <section aria-label="Opportunity" className="flex flex-col gap-3 p-4">
          <h3 className="text-sm font-semibold">Opportunity</h3>
          <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <dt className="text-xs text-muted-foreground">Customer or prospect</dt>
              <dd className="truncate text-sm" title={customerLabel}>
                {customerLabel}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Expected amount</dt>
              <dd className="text-sm">{formatCurrency(opportunity.expected_amount)}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Expected close date</dt>
              <dd className="text-sm">{formatDate(opportunity.expected_close_date)}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Agent</dt>
              <dd className="truncate text-sm" title={opportunity.sales_agent_label ?? undefined}>
                {opportunity.sales_agent_label ?? 'Unassigned'}
              </dd>
            </div>
          </dl>
        </section>
      </Card>

      <Card>
        <section aria-label="Products" className="flex flex-col gap-3 p-4">
          <h3 className="text-sm font-semibold">Products</h3>
          {lines.length === 0 ? (
            <p className="text-sm text-muted-foreground">No products yet</p>
          ) : (
            <ul className="flex flex-col divide-y rounded-lg border">
              {lines.map((line) => (
                <li key={line.id} className="flex items-center justify-between gap-2 px-3 py-2 text-sm">
                  <span className="truncate" title={`${line.product_code} - ${line.product_name}`}>
                    {line.product_code} - {line.product_name}
                  </span>
                  <span className="text-muted-foreground">{line.qty}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </Card>

      <Card>
        <section aria-label="Stage" className="flex flex-col gap-3 p-4">
          <h3 className="text-sm font-semibold">Stage</h3>
          {/* Reviewer should-fix 3: once a move has landed, say what it landed with -
              otherwise the linked order/reason only ever appeared during the confirm step
              that set it, never again after. */}
          {opportunity.sales_order_no ? (
            <p className="text-sm text-muted-foreground">
              Sales order:{' '}
              <span className="font-medium text-foreground">{opportunity.sales_order_no}</span>
            </p>
          ) : null}
          {opportunity.lost_reason_label ? (
            <p className="text-sm text-muted-foreground">
              Lost reason:{' '}
              <span className="font-medium text-foreground">{opportunity.lost_reason_label}</span>
            </p>
          ) : null}
          {transitions.length === 0 ? (
            <p className="text-sm text-muted-foreground">This is the last stage.</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {transitions.map((t) => (
                <Button
                  key={t.to_status_id}
                  type="button"
                  variant={pending?.to_status_id === t.to_status_id ? 'primary' : 'outline'}
                  size="sm"
                  onClick={() => setPending(t)}
                >
                  {t.label}
                </Button>
              ))}
            </div>
          )}

          {pending ? (
            <div className="flex flex-col gap-3 rounded-lg border p-3">
              {pending.key === 'lost' ? (
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="opportunity-lost-reason">Lost reason</Label>
                  <SearchableSelect
                    id="opportunity-lost-reason"
                    aria-label="Lost reason"
                    value={lostReason}
                    onChange={setLostReason}
                    options={lostReasonOptions}
                    placeholder="Pick a reason"
                    wrapOptions
                  />
                </div>
              ) : null}
              {pending.key === 'won' ? (
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="opportunity-sales-order">Sales order (optional)</Label>
                  <SearchableSelect
                    id="opportunity-sales-order"
                    aria-label="Sales order"
                    value={salesOrderId}
                    onChange={setSalesOrderId}
                    fetchOptions={fetchSalesOrderOptions}
                    placeholder="Search sales orders..."
                    clearable
                    wrapOptions
                  />
                </div>
              ) : null}
              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  size="sm"
                  onClick={confirmMove}
                  disabled={(pending.key === 'lost' && !lostReason) || save.isPending}
                >
                  {save.isPending ? <LoaderCircleIcon className="size-4 animate-spin" /> : null}
                  Confirm
                </Button>
                <Button type="button" variant="outline" size="sm" onClick={() => setPending(null)}>
                  Cancel
                </Button>
              </div>
            </div>
          ) : null}
        </section>
      </Card>
    </div>
  );
}
