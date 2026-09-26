'use client';

/**
 * Portal Sales Opportunity detail (UAC S2-11): stage buttons come from
 * `available_transitions` only; Lost reveals a required reason select.
 */
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
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
  getPortalSalesOpportunity,
  updatePortalSalesOpportunity,
  type PortalSalesOpportunity,
} from '../../lib/sales-opportunity-service';

/** The backend's seeded defaults - a synchronous fallback so the reason picker has
 * something to offer the instant Lost is chosen. */
const FALLBACK_LOST_REASONS: SearchableSelectOption[] = [
  { value: 'price', label: 'Price' },
  { value: 'competitor', label: 'Went to competitor' },
  { value: 'project_cancelled', label: 'Project cancelled' },
  { value: 'no_response', label: 'No response' },
  { value: 'other', label: 'Other' },
];

export function SalesOpportunityPortalDetail({ id }: { id: string }) {
  const router = useRouter();
  const [opportunity, setOpportunity] = useState<PortalSalesOpportunity | null>(null);
  const [loading, setLoading] = useState(true);
  const [pendingStatusId, setPendingStatusId] = useState<string | null>(null);
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

  const pending = opportunity.available_transitions.find((t) => t.to_status_id === pendingStatusId);

  const confirmMove = async () => {
    if (!pending) return;
    if (pending.key === 'lost' && !lostReason) return;
    setSaving(true);
    try {
      await updatePortalSalesOpportunity(id, {
        status_id: pending.to_status_id,
        ...(pending.key === 'lost' ? { lost_reason: lostReason } : {}),
      });
      toast.success('Opportunity updated');
      setPendingStatusId(null);
      setLostReason('');
      load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to update the opportunity.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="mx-auto w-full max-w-2xl space-y-4 px-3 pb-8 pt-4">
      <Button variant="ghost" size="sm" onClick={() => router.push('/portal/sales_opportunity')}>
        <ArrowLeft className="mr-1 size-4" /> Back
      </Button>

      <Card>
        <CardContent className="flex flex-col gap-2 py-4">
          <div className="flex items-center justify-between gap-2">
            <span className="text-sm font-semibold">{opportunity.title}</span>
            <Badge appearance="light">{opportunity.stage_label}</Badge>
          </div>
          <span className="text-xs text-muted-foreground">
            {opportunity.opportunity_no} &middot;{' '}
            {opportunity.customer_name ?? opportunity.prospect_name ?? '-'}
          </span>
          <div className="flex items-center justify-between text-sm">
            <span>{formatCurrency(opportunity.expected_amount)}</span>
            <span>{formatDate(opportunity.expected_close_date)}</span>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="flex flex-col gap-3 py-4">
          <span className="text-sm font-semibold">Move stage</span>
          {opportunity.available_transitions.length === 0 ? (
            <p className="text-sm text-muted-foreground">This is the last stage.</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {opportunity.available_transitions.map((t) => (
                <Button
                  key={t.to_status_id}
                  type="button"
                  variant={pendingStatusId === t.to_status_id ? 'primary' : 'outline'}
                  size="sm"
                  onClick={() => setPendingStatusId(t.to_status_id)}
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
                  <Label htmlFor="Lost reason">Lost reason</Label>
                  <SearchableSelect
                    id="Lost reason"
                    value={lostReason}
                    onChange={setLostReason}
                    options={FALLBACK_LOST_REASONS}
                    placeholder="Pick a reason"
                    wrapOptions
                  />
                </div>
              ) : null}
              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  size="sm"
                  onClick={confirmMove}
                  disabled={(pending.key === 'lost' && !lostReason) || saving}
                >
                  {saving ? <LoaderCircleIcon className="size-4 animate-spin" /> : null}
                  Confirm
                </Button>
                <Button type="button" variant="outline" size="sm" onClick={() => setPendingStatusId(null)}>
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
