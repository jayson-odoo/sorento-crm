'use client';

import Link from 'next/link';
import { useState } from 'react';
import { Download, Loader2 } from 'lucide-react';
import { SectionSkeleton } from '@/components/common/SectionSkeleton';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useConfirmPull, useDownloadPullXlsx, usePull } from '../hooks/useAutocountPull';
import { isCompareFullMatch } from '../types/compareMatch';
import { PullChangesTab } from './PullChangesTab';
import { PullExcelViewTab } from './PullExcelViewTab';
import { PullCompareTab } from './PullCompareTab';
import type {
  AutocountPull,
  AutocountPullEntity,
  AutocountPullPhase,
  ProductPullCounts,
  StockPullCounts,
} from '../types/autocountPull.types';

const PHASE_LABEL: Record<AutocountPullPhase, string> = {
  building: 'Building',
  previewing: 'Preparing',
  review: 'Awaiting confirm',
  confirmed: 'Confirmed',
  failed: 'Failed',
  expired: 'Expired',
};

const PHASE_VARIANT: Record<AutocountPullPhase, 'info' | 'warning' | 'success' | 'destructive'> = {
  building: 'info',
  previewing: 'info',
  review: 'warning',
  confirmed: 'success',
  failed: 'destructive',
  expired: 'destructive',
};

const ENTITY_LABEL: Record<AutocountPullEntity, string> = {
  products: 'AutoCount products pull',
  stock_balances: 'AutoCount stock pull',
};

/** Known `pull.warnings` codes only - an unrecognised code renders nothing rather than a
 * raw slug (captain ruling, SR4 fix round). */
const WARNING_LABEL: Record<string, string> = {
  stock_list_not_archived: 'Stock List file was not replaced',
  content_hash_mismatch: 'Snapshot checksum did not match',
};

/** dd/MM/yyyy HH:mm, Malaysia time - the one place this page states a snapshot time. */
function formatSnapshotTime(iso?: string | null): string {
  if (!iso) return '-';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '-';
  const parts = new Intl.DateTimeFormat('en-GB', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'Asia/Kuala_Lumpur',
  }).formatToParts(date);
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? '';
  return `${get('day')}/${get('month')}/${get('year')} ${get('hour')}:${get('minute')}`;
}

function productCounters(counts: ProductPullCounts) {
  return [
    { label: 'Received', value: counts.received },
    { label: 'New', value: counts.new },
    { label: 'Changed', value: counts.changed },
    { label: 'Unchanged', value: counts.unchanged },
    { label: 'Failed', value: counts.failed },
    { label: 'Price to 0', value: counts.price_to_zero },
    { label: 'Left out by AutoCount', value: counts.left_out },
  ];
}

function stockCounters(counts: StockPullCounts) {
  return [
    { label: 'Received', value: counts.received },
    { label: 'Will apply', value: counts.fed },
    { label: 'Not applied, inactive warehouse', value: counts.not_applied_inactive },
    { label: 'Not applied, unknown location', value: counts.not_applied_unknown },
    { label: 'Quantity changes', value: counts.qty_changes },
    { label: 'Set to 0', value: counts.set_to_zero },
    { label: 'Skipped, product not found', value: counts.skipped_product_not_found },
    { label: 'Negative in AutoCount', value: counts.negative_in_autocount },
  ];
}

function compareSummaryLine(pull: AutocountPull): string | null {
  const compare = pull.compare;
  if (!compare) return null;
  if (isCompareFullMatch(compare)) {
    return `100% match. ${compare.matched} of ${compare.total} items agree with ${compare.filename}.`;
  }
  const parts = [`${compare.matched} of ${compare.total} match`];
  if (compare.different) parts.push(`${compare.different} differ`);
  if (compare.only_in_excel) parts.push(`${compare.only_in_excel} only in your Excel`);
  if (compare.only_in_pull) parts.push(`${compare.only_in_pull} only in AutoCount`);
  return `${parts.join(', ')} against ${compare.filename}.`;
}

export interface AutocountPullReviewProps {
  jobId: string;
}

export function AutocountPullReview({ jobId }: AutocountPullReviewProps) {
  const [tab, setTab] = useState('changes');
  const { data: pull, isLoading } = usePull(jobId);
  const downloadMutation = useDownloadPullXlsx();
  const confirmMutation = useConfirmPull();

  if (isLoading || !pull) {
    return (
      <Card>
        <CardContent className="py-10">
          <SectionSkeleton rows={3} />
        </CardContent>
      </Card>
    );
  }

  const isBuilding = pull.phase === 'building' || pull.phase === 'previewing';
  const inReview = pull.phase === 'review' || pull.phase === 'confirmed';
  const isDead = pull.phase === 'failed' || pull.phase === 'expired';
  const counts = pull.counts;
  const counters = counts
    ? pull.entity === 'products'
      ? productCounters(counts as ProductPullCounts)
      : stockCounters(counts as StockPullCounts)
    : [];
  const downloadLabel = pull.entity === 'products' ? 'Download xlsx' : 'Download Stock List';
  const summaryLine = compareSummaryLine(pull);

  return (
    <Card>
      <CardHeader className="block space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={PHASE_VARIANT[pull.phase]} appearance="light">
            {PHASE_LABEL[pull.phase]}
          </Badge>
          <span className="text-sm font-medium">
            {ENTITY_LABEL[pull.entity]}, {pull.company_code}
          </span>
          {inReview && (
            <span className="text-xs text-muted-foreground">
              Snapshot {formatSnapshotTime(pull.header?.extractedAt)}, valid until{' '}
              {formatSnapshotTime(pull.header?.expiresAt)}
            </span>
          )}
          <span className="grow" />
          {(pull.phase === 'review' || pull.phase === 'confirmed') && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => downloadMutation.mutate(jobId)}
              disabled={downloadMutation.isPending}
            >
              <Download className="size-4" />
              {downloadMutation.isPending ? 'Preparing…' : downloadLabel}
            </Button>
          )}
          {pull.phase === 'review' && (
            <Button
              size="sm"
              onClick={() => confirmMutation.mutate(jobId)}
              disabled={Boolean(pull.confirm_blocked_reason) || confirmMutation.isPending}
            >
              {confirmMutation.isPending ? 'Confirming…' : 'Confirm'}
            </Button>
          )}
          {pull.phase === 'confirmed' && pull.apply_job_id && (
            <Button asChild variant="outline" size="sm">
              <Link href={`/system-management/import-jobs/${pull.apply_job_id}`}>
                View apply job
              </Link>
            </Button>
          )}
        </div>
        {pull.phase === 'review' && pull.confirm_blocked_reason && (
          <p className="text-xs text-destructive">{pull.confirm_blocked_reason}</p>
        )}
        {/* Advisory, not destructive (fix round 3, item 3) - the repo's warning token
            (`--warning`, `css/config.reui.css`), never `text-destructive`. */}
        {(pull.warnings ?? [])
          .filter((code) => WARNING_LABEL[code])
          .map((code) => (
            <p key={code} className="text-xs text-warning">
              {WARNING_LABEL[code]}
            </p>
          ))}
        {summaryLine && <p className="text-xs text-muted-foreground">{summaryLine}</p>}
      </CardHeader>

      <CardContent className="space-y-4">
        {isBuilding && (
          <div className="space-y-2">
            {pull.phase === 'previewing' && pull.preview_progress ? (
              // B3 (small-fix track): the preview's own row-by-row progress - the SAME
              // bar the Building state uses above, "N of M" instead of "Page N of M".
              <>
                <Progress
                  value={
                    (pull.preview_progress.processed / Math.max(pull.preview_progress.total, 1)) * 100
                  }
                />
                <p className="text-xs text-muted-foreground">
                  {pull.preview_progress.processed.toLocaleString()} of{' '}
                  {pull.preview_progress.total.toLocaleString()}
                </p>
              </>
            ) : pull.progress ? (
              <>
                <Progress value={(pull.progress.pagesDone / Math.max(pull.progress.pagesTotal, 1)) * 100} />
                <p className="text-xs text-muted-foreground">
                  Page {pull.progress.pagesDone} of {pull.progress.pagesTotal}
                  {pull.progress.stage ? ` · ${pull.progress.stage}` : ''}
                </p>
              </>
            ) : (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" aria-label="Loading" />
              </div>
            )}
          </div>
        )}

        {isDead && (
          <p className="text-sm text-destructive">
            {pull.error ?? 'The pull failed.'}
          </p>
        )}

        {inReview && (
          <>
            {counters.length > 0 && (
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                {counters.map((item) => (
                  <div key={item.label} className="rounded-lg border bg-muted/30 px-3 py-2">
                    <p className="text-lg font-semibold tabular-nums">{item.value.toLocaleString()}</p>
                    <p className="text-xs text-muted-foreground">{item.label}</p>
                  </div>
                ))}
              </div>
            )}

            <Tabs value={tab} onValueChange={setTab} className="w-full">
              <TabsList variant="line" className="w-full justify-start">
                <TabsTrigger value="changes">Changes</TabsTrigger>
                <TabsTrigger value="excel-view">Excel view</TabsTrigger>
                <TabsTrigger value="compare">Compare with my Excel</TabsTrigger>
              </TabsList>
              <TabsContent value="changes" className="mt-3 focus-visible:outline-none">
                <PullChangesTab jobId={jobId} />
              </TabsContent>
              <TabsContent value="excel-view" className="mt-3 focus-visible:outline-none">
                <PullExcelViewTab jobId={jobId} entity={pull.entity} />
              </TabsContent>
              <TabsContent value="compare" className="mt-3 focus-visible:outline-none">
                <PullCompareTab jobId={jobId} entity={pull.entity} />
              </TabsContent>
            </Tabs>
          </>
        )}
      </CardContent>
    </Card>
  );
}

export default AutocountPullReview;
