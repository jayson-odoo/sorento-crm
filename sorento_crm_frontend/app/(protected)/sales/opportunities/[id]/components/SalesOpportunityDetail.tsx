'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { LoaderCircleIcon, Plus, SquarePen } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import DetailActions from '@/components/common/DetailActions';
import { RecordNavigation } from '@/components/common/RecordNavigation';
import { SearchableSelect, type SearchableSelectOption } from '@/components/common/SearchableSelect';
import { useHasPermission } from '@/hooks/usePermissions';
import { formatCurrency, formatDate, formatDateTimeInMalaysia } from '@/lib/helpers';
import { getSalesOpportunitySalesOrderOptions } from '../../services/salesOpportunityService';
import {
  useSalesOpportunities,
  useSalesOpportunity,
  useSalesOpportunityAgentOptions,
  useSalesOpportunityMeta,
  useSaveSalesOpportunity,
} from '../../hooks/useSalesOpportunities';
import { useSalesOpportunityActions } from '../../actions';
import { OpportunityLineRow, nextLineKey, type LineDraft } from '../../components/OpportunityLineRow';
import {
  BLOCKED_VALUE,
  PROSPECT_PREFIX,
  fetchCustomerOrProspectOptions,
} from '../../lib/customerOrProspect';
import type { SalesOpportunityTransition } from '../../types/salesOpportunity.types';

/**
 * `/sales/opportunities/{id}` detail page (UAC S2-11, S2-12, S2-13; plan section 16; Phase 3
 * fix B2).
 *
 * VIEW AND EDIT ARE THE SAME LAYOUT (CLAUDE.md CRUD standard): Edit swaps title, customer or
 * prospect, agent, amount, close date and the product lines for inputs, in place - nothing
 * moves. Stage buttons come only from `available_transitions`, never guessed at; Lost
 * requires a reason from the lookup, Won offers an optional sales order limited to the
 * customer. Delete is a deferred action (D7), same shape `SalesTeamDetail` uses. Every
 * section - Opportunity, Products, Stage - renders with an empty state.
 */
export default function SalesOpportunityDetail({ id }: { id: string }) {
  const router = useRouter();
  const canEdit = useHasPermission('sales.opportunities.edit');
  const { data: opportunity, isLoading, isError } = useSalesOpportunity(id);
  const { data: meta } = useSalesOpportunityMeta();
  const { data: agentOptions } = useSalesOpportunityAgentOptions();
  const save = useSaveSalesOpportunity();
  const { actions, pending: pendingDelete } = useSalesOpportunityActions(opportunity, {
    onDeleted: () => router.push('/sales/opportunities'),
  });

  // Prev/next over the default (unfiltered) list, same simplification
  // SalesTeamDetail's own pager makes - capped at 200 rather than truly unbounded.
  const { data: list } = useSalesOpportunities({ pageIndex: 0, pageSize: 200, sorting: [], searchQuery: '' });
  const rows = list?.data ?? [];
  const index = rows.findIndex((r) => r.id === id);

  const [pending, setPending] = useState<SalesOpportunityTransition | null>(null);
  const [lostReason, setLostReason] = useState('');
  const [salesOrderId, setSalesOrderId] = useState('');

  const [isEditing, setIsEditing] = useState(false);
  const [title, setTitle] = useState('');
  const [customerOrProspect, setCustomerOrProspect] = useState('');
  const [salesAgentId, setSalesAgentId] = useState('');
  const [expectedAmount, setExpectedAmount] = useState('');
  const [expectedCloseDate, setExpectedCloseDate] = useState('');
  const [lines, setLines] = useState<LineDraft[]>([]);

  useEffect(() => {
    setPending(null);
    setLostReason('');
    setSalesOrderId('');
    setIsEditing(false);
  }, [id]);

  const lostReasonOptions: SearchableSelectOption[] = (meta?.lost_reasons ?? []).map((r) => ({
    value: r.value,
    label: r.label,
  }));
  const agentSelectOptions: SearchableSelectOption[] = (agentOptions ?? []).map((a) => ({
    value: a.id,
    label: a.label,
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

  const beginEdit = () => {
    setTitle(opportunity.title);
    setCustomerOrProspect(
      opportunity.customer_id ?? (opportunity.prospect_name ? `${PROSPECT_PREFIX}${opportunity.prospect_name}` : ''),
    );
    setSalesAgentId(opportunity.sales_agent_id ?? '');
    setExpectedAmount(String(opportunity.expected_amount ?? ''));
    setExpectedCloseDate(opportunity.expected_close_date ?? '');
    setLines(
      (opportunity.lines ?? []).map((line) => ({
        key: nextLineKey(),
        productId: line.product_id,
        qty: String(line.qty),
        productLabel: `${line.product_code} - ${line.product_name}`,
      })),
    );
    setIsEditing(true);
  };

  const addLine = () => setLines((prev) => [...prev, { key: nextLineKey(), productId: '', qty: '1' }]);
  const removeLine = (key: string) => setLines((prev) => prev.filter((l) => l.key !== key));
  const updateLine = (key: string, patch: Partial<LineDraft>) =>
    setLines((prev) => prev.map((l) => (l.key === key ? { ...l, ...patch } : l)));

  const customerLabel = opportunity.customer_name ?? opportunity.prospect_name ?? 'No customer yet';
  const existingLines = opportunity.lines ?? [];
  const transitions = opportunity.available_transitions ?? [];
  const isProspect = customerOrProspect.startsWith(PROSPECT_PREFIX);
  const canSaveEdit =
    customerOrProspect !== BLOCKED_VALUE &&
    title.trim().length > 0 &&
    !!expectedAmount &&
    !!expectedCloseDate &&
    !save.isPending;

  const handleSaveEdit = async () => {
    if (!canSaveEdit) return;
    try {
      await save.mutateAsync({
        id,
        title: title.trim(),
        expected_amount: expectedAmount,
        expected_close_date: expectedCloseDate,
        sales_agent_id: salesAgentId || null,
        ...(isProspect
          ? { prospect_name: customerOrProspect.slice(PROSPECT_PREFIX.length) }
          : { customer_id: customerOrProspect }),
        lines: lines
          .filter((l) => l.productId)
          .map((l) => ({ product_id: l.productId, qty: Number(l.qty) || 0 })),
      });
      setIsEditing(false);
    } catch {
      // The hook toasted the reason; the session stays open so nothing typed is lost.
    }
  };

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
            {isEditing ? (
              <div className="flex flex-col gap-1">
                <Label htmlFor="opportunity-edit-title" className="text-xs text-muted-foreground">
                  Title
                </Label>
                <Input
                  id="opportunity-edit-title"
                  value={title}
                  maxLength={200}
                  onChange={(e) => setTitle(e.target.value)}
                  className="h-8 w-64 max-w-full"
                />
              </div>
            ) : (
              <h2 className="truncate text-lg font-semibold" title={opportunity.title}>
                {opportunity.title}
              </h2>
            )}
            <Badge appearance="light">{opportunity.stage_label}</Badge>
          </div>
          {isEditing ? (
            <div className="flex shrink-0 flex-wrap items-center gap-2">
              <Button variant="outline" size="sm" onClick={() => setIsEditing(false)} disabled={save.isPending}>
                Cancel
              </Button>
              <Button size="sm" onClick={handleSaveEdit} disabled={!canSaveEdit}>
                {save.isPending ? <LoaderCircleIcon className="size-4 animate-spin" /> : null}
                Save
              </Button>
            </div>
          ) : (
            <DetailActions
              pagerNode={
                <RecordNavigation
                  index={index >= 0 ? index + 1 : null}
                  total={rows.length}
                  hasPrevious={index > 0}
                  hasNext={index >= 0 && index < rows.length - 1}
                  onPrevious={() => router.push(`/sales/opportunities/${rows[index - 1].id}`)}
                  onNext={() => router.push(`/sales/opportunities/${rows[index + 1].id}`)}
                  ariaLabel="sales opportunity"
                />
              }
              actions={actions}
              pendingAction={pendingDelete}
              primary={
                canEdit ? (
                  <Button variant="primary" size="sm" className="gap-1.5" onClick={beginEdit}>
                    <SquarePen className="size-4" />
                    Edit
                  </Button>
                ) : undefined
              }
            />
          )}
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
          {isEditing ? (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="opportunity-edit-customer">Customer or prospect</Label>
                <SearchableSelect
                  id="opportunity-edit-customer"
                  aria-label="Customer or prospect"
                  value={customerOrProspect}
                  onChange={setCustomerOrProspect}
                  fetchOptions={fetchCustomerOrProspectOptions}
                  selectedOption={
                    opportunity.customer_id
                      ? { value: opportunity.customer_id, label: customerLabel }
                      : undefined
                  }
                  placeholder="Search customers..."
                  wrapOptions
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="opportunity-edit-amount">Expected amount</Label>
                <Input
                  id="opportunity-edit-amount"
                  type="number"
                  min="0"
                  step="0.01"
                  value={expectedAmount}
                  onChange={(e) => setExpectedAmount(e.target.value)}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="opportunity-edit-close-date">Expected close date</Label>
                <Input
                  id="opportunity-edit-close-date"
                  type="date"
                  value={expectedCloseDate}
                  onChange={(e) => setExpectedCloseDate(e.target.value)}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="opportunity-edit-agent">Agent</Label>
                <SearchableSelect
                  id="opportunity-edit-agent"
                  aria-label="Agent"
                  value={salesAgentId}
                  onChange={setSalesAgentId}
                  options={agentSelectOptions}
                  placeholder="Unassigned"
                  clearable
                  wrapOptions
                />
              </div>
            </div>
          ) : (
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
          )}
        </section>
      </Card>

      <Card>
        <section aria-label="Products" className="flex flex-col gap-3 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-sm font-semibold">Products</h3>
            {isEditing ? (
              <Button type="button" variant="outline" size="sm" onClick={addLine}>
                <Plus className="size-4" />
                Add product
              </Button>
            ) : null}
          </div>
          {isEditing ? (
            lines.length === 0 ? (
              <p className="text-sm text-muted-foreground">No products yet</p>
            ) : (
              <div className="flex flex-col gap-2">
                {lines.map((line) => (
                  <OpportunityLineRow
                    key={line.key}
                    line={line}
                    onChange={(patch) => updateLine(line.key, patch)}
                    onRemove={() => removeLine(line.key)}
                  />
                ))}
              </div>
            )
          ) : existingLines.length === 0 ? (
            <p className="text-sm text-muted-foreground">No products yet</p>
          ) : (
            <ul className="flex flex-col divide-y rounded-lg border">
              {existingLines.map((line) => (
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
                  disabled={isEditing}
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
