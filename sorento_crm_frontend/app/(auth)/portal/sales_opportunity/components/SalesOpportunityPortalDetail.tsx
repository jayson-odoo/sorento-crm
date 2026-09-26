'use client';

/**
 * Portal Sales Opportunity detail (UAC S2-11): stage buttons come from
 * `available_transitions` only; Lost reveals a required reason select sourced from the
 * shared meta endpoint's `lost_reasons` (same values the CRM detail page offers). Every
 * other transition (Qualified, Won, ...) applies the moment its button is clicked - only
 * Lost needs a second, explicit confirm, because only it collects an extra field first.
 *
 * No `useRouter` - this component is unit-tested without a Next.js router context, so
 * navigation is plain `<Link>`s throughout, same as `SalesOpportunityPortalList`.
 */
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { ArrowLeft, LoaderCircleIcon } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { SearchableSelect, type SearchableSelectOption } from '@/components/common/SearchableSelect';
import { toast } from '@/lib/toast';
import { formatCurrency, formatDate } from '@/lib/helpers';
import {
  getPortalOpportunityMeta,
  getPortalSalesOpportunity,
  updatePortalSalesOpportunity,
  type PortalSalesOpportunity,
} from '../../lib/sales-opportunity-service';

export default function SalesOpportunityPortalDetail({ id }: { id: string }) {
  const [opportunity, setOpportunity] = useState<PortalSalesOpportunity | null>(null);
  const [loading, setLoading] = useState(true);
  const [lostReasonOptions, setLostReasonOptions] = useState<SearchableSelectOption[]>([]);
  const [pendingLost, setPendingLost] = useState(false);
  const [lostToStatusId, setLostToStatusId] = useState<string | null>(null);
  const [lostReason, setLostReason] = useState('');
  const [saving, setSaving] = useState(false);

  const load = () => {
    setLoading(true);
    getPortalSalesOpportunity(id)
      .then(setOpportunity)
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    getPortalOpportunityMeta().then((meta) =>
      setLostReasonOptions(meta.lost_reasons.map((r) => ({ value: r.value, label: r.label }))),
    );
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

  if (!opportunity) {
    return (
      <div className="mx-auto w-full max-w-2xl px-3 pt-4 text-center text-sm text-muted-foreground">
        Sales opportunity not found.
      </div>
    );
  }

  const lines = opportunity.lines ?? [];
  const transitions = opportunity.available_transitions ?? [];

  const applyStatus = async (toStatusId: string, extra?: { lost_reason: string }) => {
    setSaving(true);
    try {
      await updatePortalSalesOpportunity(id, { status_id: toStatusId, ...extra });
      toast.success('Opportunity updated');
      setPendingLost(false);
      setLostToStatusId(null);
      setLostReason('');
      load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to update the opportunity.');
    } finally {
      setSaving(false);
    }
  };

  const handleStageClick = (key: string, toStatusId: string) => {
    if (key === 'lost') {
      setPendingLost(true);
      setLostToStatusId(toStatusId);
      return;
    }
    void applyStatus(toStatusId);
  };

  const confirmLost = () => {
    if (!lostToStatusId || !lostReason) return;
    void applyStatus(lostToStatusId, { lost_reason: lostReason });
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
            <span className="text-sm font-semibold">{opportunity.title}</span>
            <Badge appearance="light">{opportunity.stage_label}</Badge>
          </div>
          <span className="text-xs text-muted-foreground">
            <span>{opportunity.opportunity_no}</span> &middot;{' '}
            <span>{opportunity.customer_name ?? opportunity.prospect_name ?? '-'}</span>
          </span>
          <div className="flex items-center justify-between text-sm">
            <span>{formatCurrency(opportunity.expected_amount)}</span>
            <span>{formatDate(opportunity.expected_close_date)}</span>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="flex flex-col gap-3 py-4">
          <span className="text-sm font-semibold">Products</span>
          {lines.length === 0 ? (
            <p className="text-sm text-muted-foreground">No products yet</p>
          ) : (
            <ul className="flex flex-col divide-y rounded-lg border">
              {lines.map((line) => (
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
                  variant={pendingLost && lostToStatusId === t.to_status_id ? 'primary' : 'outline'}
                  size="sm"
                  disabled={saving}
                  onClick={() => handleStageClick(t.key, t.to_status_id)}
                >
                  {saving && lostToStatusId === t.to_status_id ? (
                    <LoaderCircleIcon className="size-4 animate-spin" />
                  ) : null}
                  {t.label}
                </Button>
              ))}
            </div>
          )}
          {pendingLost ? (
            <div className="flex flex-col gap-3 rounded-lg border p-3">
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
              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  size="sm"
                  onClick={confirmLost}
                  disabled={!lostReason || saving}
                >
                  {saving ? <LoaderCircleIcon className="size-4 animate-spin" /> : null}
                  Confirm
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setPendingLost(false);
                    setLostToStatusId(null);
                    setLostReason('');
                  }}
                >
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
