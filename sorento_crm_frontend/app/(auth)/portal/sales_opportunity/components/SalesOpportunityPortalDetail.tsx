'use client';

/**
 * Portal Sales Opportunity detail (UAC S2-11): stage buttons come from
 * `available_transitions` only; Lost reveals a required reason select sourced from the
 * shared meta endpoint's `lost_reasons` (same values the CRM detail page offers). Won and
 * Lost both need an explicit confirm step (reviewer should-fix 8) - closing an opportunity
 * either way is a one-way door (Phase 3 fix N7: neither can be edited again after) - every
 * other transition (Qualified, ...) applies the moment its button is clicked.
 *
 * Edit is IN PLACE (Phase 3 fix2 should-fix 5) - the SAME cards in the SAME order, title,
 * customer or prospect, amount, close date and product lines each swap for an input where
 * they stand, exactly as the CRM's own `SalesOpportunityDetail` does. An earlier round routed
 * Edit through a second `SalesOpportunityPortalForm` (the CREATE form) with an `initial` prop,
 * which replaced the whole read view with a different layout instead of editing this one;
 * reverted, and that component is create-only again.
 *
 * No `useRouter` - this component is unit-tested without a Next.js router context, so
 * navigation is plain `<Link>`s throughout, same as `SalesOpportunityPortalList`.
 */
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { ArrowLeft, LoaderCircleIcon, Plus } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { AsyncCombobox } from '../../components/AsyncCombobox';
import { SearchableSelect, type SearchableSelectOption } from '@/components/common/SearchableSelect';
import { toast } from '@/lib/toast';
import { formatCurrency, formatDate } from '@/lib/helpers';
import {
  getPortalOpportunityMeta,
  getPortalSalesOpportunity,
  updatePortalSalesOpportunity,
  type PortalSalesOpportunity,
} from '../../lib/sales-opportunity-service';
import { type CustomerComboOption, fetchCustomerOrProspectOptions } from '../lib/customerOrProspect';
import { PortalOpportunityLineRow, nextLineKey, type LineDraft } from './PortalOpportunityLineRow';

export default function SalesOpportunityPortalDetail({ id }: { id: string }) {
  const [opportunity, setOpportunity] = useState<PortalSalesOpportunity | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [lostReasonOptions, setLostReasonOptions] = useState<SearchableSelectOption[]>([]);
  const [pendingKey, setPendingKey] = useState<string | null>(null);
  const [pendingToStatusId, setPendingToStatusId] = useState<string | null>(null);
  const [lostReason, setLostReason] = useState('');
  const [saving, setSaving] = useState(false);

  const [isEditing, setIsEditing] = useState(false);
  const [title, setTitle] = useState('');
  const [customerValue, setCustomerValue] = useState('');
  const [customerId, setCustomerId] = useState<string | undefined>();
  const [prospectName, setProspectName] = useState<string | undefined>();
  const [expectedAmount, setExpectedAmount] = useState('');
  const [expectedCloseDate, setExpectedCloseDate] = useState('');
  const [lines, setLines] = useState<LineDraft[]>([]);

  const load = () => {
    setLoading(true);
    setLoadError(false);
    getPortalSalesOpportunity(id)
      .then(setOpportunity)
      .catch(() => setLoadError(true))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // The reason picker just falls back to an empty list on failure - Lost still works,
    // it only offers nothing to pick until a retry (Move stage) succeeds.
    getPortalOpportunityMeta()
      .then((meta) =>
        setLostReasonOptions(meta.lost_reasons.map((r) => ({ value: r.value, label: r.label }))),
      )
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  if (loading) {
    return (
      <div className="mx-auto w-full max-w-2xl space-y-3 px-3 pt-4">
        <Skeleton className="h-8 w-32" />
        <Skeleton className="h-40 w-full rounded-xl" />
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="mx-auto w-full max-w-2xl space-y-3 px-3 pt-4 text-center text-sm">
        <p className="text-destructive">Failed to load this opportunity.</p>
        <Button variant="outline" size="sm" onClick={load}>
          Retry
        </Button>
      </div>
    );
  }

  if (!opportunity) {
    return (
      <div className="mx-auto w-full max-w-2xl px-3 pt-4 text-center text-sm text-muted-foreground">
        Sales opportunity not found.
      </div>
    );
  }

  const lines_ = opportunity.lines ?? [];
  const transitions = opportunity.available_transitions ?? [];
  // N7 (Phase 3): once closed, the server rejects every field edit with 422
  // OPPORTUNITY_CLOSED - Edit has no reason to appear once that door is shut.
  const canEditFields = opportunity.outcome === 'open';

  const beginEdit = () => {
    setTitle(opportunity.title);
    setCustomerValue(opportunity.customer_id ? opportunity.customer_name ?? '' : opportunity.prospect_name ?? '');
    setCustomerId(opportunity.customer_id ?? undefined);
    setProspectName(opportunity.customer_id ? undefined : opportunity.prospect_name ?? undefined);
    setExpectedAmount(String(opportunity.expected_amount ?? ''));
    setExpectedCloseDate(opportunity.expected_close_date ?? '');
    setLines(
      lines_.map((line) => ({
        key: nextLineKey(),
        productId: line.product_id,
        productLabel: `${line.product_code ?? ''} - ${line.product_name ?? ''}`,
        qty: String(line.qty),
      })),
    );
    setIsEditing(true);
  };

  const handleCustomerChange = (value: string, item?: CustomerComboOption) => {
    setCustomerValue(value);
    if (item) {
      if (item.customerId) {
        setCustomerId(item.customerId);
        setProspectName(undefined);
      } else if (item.prospectName) {
        setProspectName(item.prospectName);
        setCustomerId(undefined);
      }
      return;
    }
    // Reviewer should-fix 6 (same rule the create form applies): a keystroke with no item
    // means the typed text no longer matches whatever was picked before.
    setCustomerId(undefined);
    setProspectName(undefined);
  };

  const addLine = () =>
    setLines((prev) => [...prev, { key: nextLineKey(), productId: '', productLabel: '', qty: '1' }]);
  const removeLine = (key: string) => setLines((prev) => prev.filter((l) => l.key !== key));
  const updateLine = (key: string, patch: Partial<LineDraft>) =>
    setLines((prev) => prev.map((l) => (l.key === key ? { ...l, ...patch } : l)));

  const canSaveEdit =
    title.trim().length > 0 && !!expectedAmount && !!expectedCloseDate && !saving;

  const handleSaveEdit = async () => {
    if (!canSaveEdit) return;
    setSaving(true);
    try {
      await updatePortalSalesOpportunity(id, {
        title: title.trim(),
        expected_amount: expectedAmount,
        expected_close_date: expectedCloseDate,
        // B-new (Phase 3 fix2): the OTHER key goes along as an explicit null - the
        // service fills an absent key from the row already on the opportunity, so
        // switching customer <-> prospect with the other key merely missing re-sent the
        // old value and 422'd CUSTOMER_AND_PROSPECT_TOGETHER.
        ...(prospectName
          ? { prospect_name: prospectName, customer_id: null }
          : { customer_id: customerId, prospect_name: null }),
        lines: lines
          .filter((l) => l.productId)
          .map((l) => ({ product_id: l.productId, qty: Number(l.qty) || 0 })),
      });
      toast.success('Opportunity saved');
      setIsEditing(false);
      load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to save the opportunity.');
    } finally {
      setSaving(false);
    }
  };

  const applyStatus = async (toStatusId: string, extra?: { lost_reason: string }) => {
    setSaving(true);
    try {
      await updatePortalSalesOpportunity(id, { status_id: toStatusId, ...extra });
      toast.success('Opportunity updated');
      setPendingKey(null);
      setPendingToStatusId(null);
      setLostReason('');
      load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to update the opportunity.');
    } finally {
      setSaving(false);
    }
  };

  const cancelPending = () => {
    setPendingKey(null);
    setPendingToStatusId(null);
    setLostReason('');
  };

  const handleStageClick = (key: string, toStatusId: string) => {
    // Won and Lost both close the opportunity for good (Phase 3 fix N7) - a confirm
    // step for both, not just the one that happens to collect an extra field.
    if (key === 'lost' || key === 'won') {
      setPendingKey(key);
      setPendingToStatusId(toStatusId);
      return;
    }
    void applyStatus(toStatusId);
  };

  const confirmPending = () => {
    if (!pendingToStatusId) return;
    if (pendingKey === 'lost') {
      if (!lostReason) return;
      void applyStatus(pendingToStatusId, { lost_reason: lostReason });
      return;
    }
    void applyStatus(pendingToStatusId);
  };

  return (
    <div className="mx-auto w-full max-w-2xl space-y-4 px-3 pb-8 pt-4">
      <Button variant="ghost" size="sm" asChild>
        <Link href="/portal/sales_opportunity">
          <ArrowLeft className="mr-1 size-4" /> Back
        </Link>
      </Button>

      <Card>
        <CardContent className="flex flex-col gap-2 py-4">
          <div className="flex items-center justify-between gap-2">
            {isEditing ? (
              <div className="flex flex-1 flex-col gap-1.5">
                <Label htmlFor="portal-opportunity-edit-title">Title</Label>
                <Input
                  id="portal-opportunity-edit-title"
                  aria-label="Title"
                  value={title}
                  maxLength={200}
                  onChange={(e) => setTitle(e.target.value)}
                />
              </div>
            ) : (
              <span className="text-sm font-semibold">{opportunity.title}</span>
            )}
            <Badge status={opportunity.stage_key} appearance="light">
              {opportunity.stage_label}
            </Badge>
          </div>
          <span className="text-xs text-muted-foreground">{opportunity.opportunity_no}</span>
          {isEditing ? (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="portal-opportunity-edit-customer">Customer or prospect</Label>
              <AsyncCombobox<CustomerComboOption>
                id="portal-opportunity-edit-customer"
                value={customerValue}
                onChange={handleCustomerChange}
                fetchOptions={fetchCustomerOrProspectOptions}
                optionValue={(o) => o.id}
                optionLabel={(o) => o.label}
                optionDisabled={(o) => !!o.disabled}
                placeholder="Search customer or prospect..."
                allowFreeText={false}
              />
            </div>
          ) : (
            <span className="text-xs text-muted-foreground">
              {opportunity.customer_name ?? opportunity.prospect_name ?? '-'}
            </span>
          )}
          {isEditing ? (
            <div className="grid grid-cols-2 gap-3">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="portal-opportunity-edit-amount">Expected amount</Label>
                <Input
                  id="portal-opportunity-edit-amount"
                  aria-label="Expected amount"
                  type="number"
                  min="0"
                  step="0.01"
                  value={expectedAmount}
                  onChange={(e) => setExpectedAmount(e.target.value)}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="portal-opportunity-edit-close-date">Expected close date</Label>
                <Input
                  id="portal-opportunity-edit-close-date"
                  aria-label="Expected close date"
                  type="date"
                  value={expectedCloseDate}
                  onChange={(e) => setExpectedCloseDate(e.target.value)}
                />
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-between text-sm">
              <span>{formatCurrency(opportunity.expected_amount)}</span>
              <span>{formatDate(opportunity.expected_close_date)}</span>
            </div>
          )}
          {/* Browser pass defect 1: the detail never surfaced WHY a Lost opportunity was
              lost, once it already was one - the reason only ever showed during the
              confirm step that set it. */}
          {opportunity.outcome === 'lost' && opportunity.lost_reason_label ? (
            <p className="text-sm text-muted-foreground">
              Lost reason: <span className="font-medium text-foreground">{opportunity.lost_reason_label}</span>
            </p>
          ) : null}
          {isEditing ? (
            <div className="flex items-center gap-2">
              <Button type="button" size="sm" onClick={handleSaveEdit} disabled={!canSaveEdit}>
                {saving ? <LoaderCircleIcon className="size-4 animate-spin" /> : null}
                Save
              </Button>
              <Button type="button" variant="outline" size="sm" onClick={() => setIsEditing(false)} disabled={saving}>
                Cancel
              </Button>
            </div>
          ) : canEditFields ? (
            <Button type="button" variant="outline" size="sm" className="self-start" onClick={beginEdit}>
              Edit
            </Button>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardContent className="flex flex-col gap-3 py-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-sm font-semibold">Products</span>
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
                  <PortalOpportunityLineRow
                    key={line.key}
                    line={line}
                    onChange={(patch) => updateLine(line.key, patch)}
                    onRemove={() => removeLine(line.key)}
                  />
                ))}
              </div>
            )
          ) : lines_.length === 0 ? (
            <p className="text-sm text-muted-foreground">No products yet</p>
          ) : (
            <ul className="flex flex-col divide-y rounded-lg border">
              {lines_.map((line) => (
                <li
                  key={line.id ?? line.product_id}
                  className="flex items-center justify-between gap-2 px-3 py-2 text-sm"
                >
                  <span className="min-w-0 flex-1 truncate">
                    <span>{line.product_code}</span> - <span>{line.product_name}</span>
                  </span>
                  <span className="text-muted-foreground">{line.qty}</span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardContent className="flex flex-col gap-3 py-4">
          <span className="text-sm font-semibold">Move stage</span>
          {transitions.length === 0 ? (
            <p className="text-sm text-muted-foreground">This is the last stage.</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {transitions.map((t) => (
                <Button
                  key={t.to_status_id}
                  type="button"
                  variant={pendingKey && pendingToStatusId === t.to_status_id ? 'primary' : 'outline'}
                  size="sm"
                  disabled={saving || isEditing}
                  onClick={() => handleStageClick(t.key, t.to_status_id)}
                >
                  {saving && pendingToStatusId === t.to_status_id ? (
                    <LoaderCircleIcon className="size-4 animate-spin" />
                  ) : null}
                  {t.label}
                </Button>
              ))}
            </div>
          )}
          {pendingKey ? (
            <div className="flex flex-col gap-3 rounded-lg border p-3">
              {pendingKey === 'lost' ? (
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="portal-opportunity-lost-reason">Lost reason</Label>
                  <SearchableSelect
                    id="portal-opportunity-lost-reason"
                    aria-label="Lost reason"
                    value={lostReason}
                    onChange={setLostReason}
                    options={lostReasonOptions}
                    placeholder="Pick a reason"
                    wrapOptions
                  />
                </div>
              ) : null}
              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  size="sm"
                  onClick={confirmPending}
                  disabled={(pendingKey === 'lost' && !lostReason) || saving}
                >
                  {saving ? <LoaderCircleIcon className="size-4 animate-spin" /> : null}
                  Confirm
                </Button>
                <Button type="button" variant="outline" size="sm" onClick={cancelPending}>
                  Cancel
                </Button>
              </div>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
