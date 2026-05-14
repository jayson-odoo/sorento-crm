'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useImportJobs } from '@/app/(protected)/system-management/import-jobs/hooks/useImportJobs';
import type { ImportJob } from '@/app/(protected)/system-management/import-jobs/types/importJob.types';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { formatDateTime } from '@/lib/helpers';
import { ExternalLink, Loader2, ChevronDown, ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useQueryClient } from '@tanstack/react-query';

export interface LatestImportStatusPanelProps {
  /** Job type filter (e.g. product_import, order_tracking_import, grn_listing_import, spo_import). */
  jobType: string;
  /** Optional label for the card header (e.g. "Latest products import"). */
  title?: string;
  /** Optional class name for the card container. */
  className?: string;
  /** If true, panel content is expanded by default. Default is false (collapsed). */
  defaultExpanded?: boolean;
  /** If true, show the panel even when there is no job (displays "No recent import" placeholder). */
  showWhenEmpty?: boolean;
  /** Query keys to invalidate when the latest job transitions to finished/failed. */
  invalidateQueryKeys?: readonly (readonly unknown[])[];
  /** Called when the latest job transitions from in-progress to a terminal status. */
  onJobFinished?: (job: ImportJob) => void;
}

function statusVariant(status: string): 'primary' | 'secondary' | 'success' | 'warning' | 'destructive' | 'outline' {
  switch (status) {
    case 'finished':
      return 'success';
    case 'failed':
    case 'cancelled':
      return 'destructive';
    case 'pending':
    case 'queued':
    case 'started':
      return 'warning';
    default:
      return 'secondary';
  }
}

function JobPanelContent({ job }: { job: ImportJob }) {
  const isInProgress = ['pending', 'queued', 'started'].includes(job.status);
  const total = job.total_rows ?? 0;
  const processed = job.processed_rows ?? 0;
  const pct = total > 0 ? Math.round((processed / total) * 100) : 0;

  return (
    <CardContent className="pt-0">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
        <span className="font-medium">Status</span>
        <Badge variant={statusVariant(job.status)} className="capitalize">
          {isInProgress && <Loader2 className="mr-1 size-3 animate-spin" />}
          {job.status}
        </Badge>
        {job.filename && (
          <span className="truncate text-muted-foreground" title={job.filename}>
            {job.filename}
          </span>
        )}
      </div>
      {(total > 0 || processed > 0) && (
        <div className="mt-2">
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>
              {processed} / {total} rows
              {job.successful_rows != null || job.failed_rows != null || job.skipped_rows != null
                ? ` · ${job.successful_rows ?? 0} ok, ${job.failed_rows ?? 0} failed, ${job.skipped_rows ?? 0} skipped`
                : ''}
            </span>
            {total > 0 && <span>{pct}%</span>}
          </div>
          <Progress value={total > 0 ? pct : 0} className="mt-1 h-1.5" />
        </div>
      )}
      {job.updated_at && (
        <p className="mt-2 text-xs text-muted-foreground">
          Updated {formatDateTime(job.updated_at)}
        </p>
      )}
      <Link
        href={`/system-management/import-jobs/${job.job_id}`}
        className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
      >
        View job
        <ExternalLink className="size-3" />
      </Link>
    </CardContent>
  );
}

const TERMINAL_STATUSES = new Set(['finished', 'failed', 'cancelled']);

export function LatestImportStatusPanel({
  jobType,
  title,
  className,
  defaultExpanded = false,
  showWhenEmpty = false,
  invalidateQueryKeys,
  onJobFinished,
}: LatestImportStatusPanelProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const queryClient = useQueryClient();
  const { data, isLoading, isError } = useImportJobs({
    pageIndex: 0,
    pageSize: 1,
    job_type: jobType,
  });

  const job: ImportJob | undefined = data?.data?.[0];
  const lastStatusRef = useRef<string | null>(null);

  useEffect(() => {
    if (!job) {
      lastStatusRef.current = null;
      return;
    }
    const prev = lastStatusRef.current;
    const curr = job.status;
    lastStatusRef.current = curr;
    if (prev && prev !== curr && !TERMINAL_STATUSES.has(prev) && TERMINAL_STATUSES.has(curr)) {
      invalidateQueryKeys?.forEach((key) => {
        queryClient.invalidateQueries({ queryKey: [...key] });
      });
      onJobFinished?.(job);
    }
  }, [job, invalidateQueryKeys, onJobFinished, queryClient]);

  if (isLoading && !job) {
    return (
      <Card className={className}>
        <CardHeader className="py-3">
          <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />
            Loading…
          </div>
        </CardHeader>
      </Card>
    );
  }

  if (!showWhenEmpty && (isError || !job)) {
    return null;
  }

  if (showWhenEmpty && !job && !isLoading) {
    return (
      <Card className={className}>
        <CardHeader className="py-3">
          <div className="flex items-center gap-2">
            <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
            <span className="text-sm font-medium text-muted-foreground">
              {title ?? 'Latest import'}
            </span>
            <span className="text-xs text-muted-foreground ml-2">No recent import</span>
          </div>
        </CardHeader>
      </Card>
    );
  }

  if (!job) return null;

  return (
    <Card className={className}>
      <CardHeader className="py-3">
        <Button
          variant="ghost"
          size="sm"
          className="h-auto w-full justify-start gap-2 p-0 font-medium hover:bg-transparent"
          onClick={() => setExpanded((e) => !e)}
          aria-expanded={expanded}
        >
          {expanded ? (
            <ChevronDown className="size-4 shrink-0" />
          ) : (
            <ChevronRight className="size-4 shrink-0" />
          )}
          <span className="text-sm">{title ?? 'Latest import'}</span>
          <Badge variant={statusVariant(job.status)} className="ml-auto capitalize">
            {job.status}
          </Badge>
        </Button>
      </CardHeader>
      {expanded && <JobPanelContent job={job} />}
    </Card>
  );
}
