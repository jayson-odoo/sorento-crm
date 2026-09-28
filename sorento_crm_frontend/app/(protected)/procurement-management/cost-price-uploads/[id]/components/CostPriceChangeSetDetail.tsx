'use client';

import { useCallback, useMemo } from 'react';
import { Download, Trash2 } from 'lucide-react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { PageHeader } from '@/components/common/PageHeader';
import DetailActions from '@/components/common/DetailActions';
import type { RecordAction } from '@/components/common/recordActions';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { formatStatusLabel } from '@/lib/status-badge';
import {
  costPriceChangeSetsPagerQuery,
  useCostPriceChangeSet,
  useRefreshCostPricePrices,
} from '../../hooks/useCostPriceChangeSets';
import { useDeferredAction } from '@/hooks/useDeferredAction';
import { downloadCostPriceSourceFile } from '../../services/costPriceService';
import { formatPlainDate } from '../../lib/formatPlainDate';
import { CostPriceApplyButton } from './CostPriceApplyButton';
import { CostPriceHistoryTab } from './CostPriceHistoryTab';
import { CostPriceLinesTab } from './CostPriceLinesTab';

function validityLabel(startDate: string | null, endDate: string | null): string {
  if (!startDate && !endDate) return 'Always';
  if (startDate && !endDate) return `Valid from ${formatPlainDate(startDate)}, no end`;
  if (!startDate && endDate) return `Valid until ${formatPlainDate(endDate)}`;
  return `Valid from ${formatPlainDate(startDate)} to ${formatPlainDate(endDate)}`;
}

export function sheetsAndRowsLabel(sheets: number, rows: number): string {
  return `${sheets} ${sheets === 1 ? 'sheet' : 'sheets'}, ${rows} ${rows === 1 ? 'row' : 'rows'}`;
}

export function CostPriceChangeSetDetail({ changeSetId }: { changeSetId: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { data: changeSet, isLoading } = useCostPriceChangeSet(changeSetId);

  const activeTab = searchParams.get('tab') || 'lines';
  const handleTabChange = useCallback(
    (tab: string) => {
      const params = new URLSearchParams(searchParams.toString());
      if (tab === 'lines') params.delete('tab');
      else params.set('tab', tab);
      const qs = params.toString();
      router.replace(`${pathname}${qs ? `?${qs}` : ''}`, { scroll: false });
    },
    [pathname, router, searchParams],
  );

  const discard = useDeferredAction({
    actionKey: 'cost_price_change_set.discard',
    entityType: 'cost_price_change_set',
    entityId: changeSetId,
    verb: 'Discarding',
    subject: changeSet?.code ?? 'this set',
    surface: 'inline',
    successMessage: 'Discarded.',
    onCommitted: () => router.push('/procurement-management/cost-price-uploads'),
  });

  const refreshPrices = useRefreshCostPricePrices(changeSetId);

  // Round 6 R1 (owner, 28 Sep 2026): Download file and Discard live in the gear, Discard last
  // in red; Discard stays the deferred countdown it was (D7), never a confirm dialog.
  const hasSourceFile = changeSet?.has_source_file ?? false;
  const canDiscard = changeSet?.actions.can_discard ?? false;
  const gearActions = useMemo<RecordAction[]>(() => {
    const items: RecordAction[] = [
      {
        key: 'cost_price_change_set.download',
        label: 'Download file',
        icon: Download,
        disabled: !hasSourceFile,
        run: () => void downloadCostPriceSourceFile(changeSetId),
      },
    ];
    if (canDiscard) {
      items.push({ key: 'cost_price_change_set.discard', label: 'Discard', icon: Trash2, kind: 'destructive', run: () => discard.start() });
    }
    return items;
  }, [canDiscard, changeSetId, discard, hasSourceFile]);

  if (isLoading || !changeSet) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title={
          <span className="flex items-center gap-2">
            {changeSet.code}
            <Badge status={changeSet.status}>{formatStatusLabel(changeSet.status)}</Badge>
          </span>
        }
        crumbTitle={changeSet.code}
        actions={
          // `shrink-0` + no wrap from sm up: the long supplier line beside it must not push
          // Apply under the gear (browser pass at 1280, round 6 R1: top right, one row).
          <div className="flex flex-wrap items-center justify-end gap-2 sm:shrink-0 sm:flex-nowrap">
            {changeSet.actions.can_refresh_prices ? (
              <Button variant="outline" onClick={() => void refreshPrices.mutateAsync()} disabled={refreshPrices.isPending}>
                Refresh costs
              </Button>
            ) : null}
            <DetailActions
              pager={{
                ...costPriceChangeSetsPagerQuery,
                detailPath: '/procurement-management/cost-price-uploads',
                currentId: changeSetId,
                ariaLabel: 'cost upload',
              }}
              actions={gearActions}
              primary={<CostPriceApplyButton changeSet={changeSet} />}
              pendingAction={discard.countdown}
              className="sm:flex-nowrap"
            />
          </div>
        }
      />
      <p className="text-sm text-muted-foreground">
        {changeSet.supplier.supplier_name} &middot; {changeSet.currency} &middot; {validityLabel(changeSet.start_date, changeSet.end_date)}
        {changeSet.uploaded_by_name ? <> &middot; uploaded by {changeSet.uploaded_by_name} {formatDateTimeInMalaysia(changeSet.created_at)}</> : null}
        {changeSet.total_rows ? <> &middot; {sheetsAndRowsLabel(changeSet.sheets.length, changeSet.total_rows)}</> : null}
        {changeSet.status === 'applied' ? (
          <>
            {' '}
            &middot; applied by {changeSet.applied_by_name ?? 'a Sorento user'}
            {changeSet.applied_at ? <> {formatDateTimeInMalaysia(changeSet.applied_at)}</> : null}
            {changeSet.verified != null ? (
              <>
                {' '}
                &middot; {changeSet.verified ? `Verified by ${changeSet.applied_by_name ?? 'a Sorento user'}` : 'Not verified'}
              </>
            ) : null}
          </>
        ) : null}
      </p>

      {changeSet.status === 'pending_verification' ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          <p className="font-medium">
            Submitted by {changeSet.submitted_by_name ?? 'a Sorento user'}
            {changeSet.submitted_at ? `, ${formatDateTimeInMalaysia(changeSet.submitted_at)}` : ''}.
          </p>
        </div>
      ) : null}

      {changeSet.status === 'draft' && changeSet.returned_reason ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          <p className="font-medium">Returned by {changeSet.returned_by_name ?? 'a verifier'}</p>
          <p>{changeSet.returned_reason}</p>
        </div>
      ) : null}

      <Tabs value={activeTab} onValueChange={handleTabChange}>
        <TabsList variant="line" className="w-full justify-start">
          <TabsTrigger value="lines">Lines</TabsTrigger>
          <TabsTrigger value="history">History</TabsTrigger>
        </TabsList>
        <TabsContent value="lines">
          <CostPriceLinesTab changeSet={changeSet} />
        </TabsContent>
        <TabsContent value="history">
          <CostPriceHistoryTab setId={changeSetId} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

export default CostPriceChangeSetDetail;
