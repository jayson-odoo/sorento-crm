'use client';

import { use } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { MoveLeft, ChevronLeft, ChevronRight, Download } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';
import { Button } from '@/components/ui/button';
import { Container } from '@/components/common/container';
import { Toolbar, ToolbarActions, ToolbarHeading, ToolbarTitle } from '@/components/common/toolbar';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Progress } from '@/components/ui/progress';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { getStatusBadgeVariant } from '@/lib/status-badge';
import {
  getImportJob,
  getImportJobStatus,
  getImportJobs,
  downloadImportJobSourceFile,
} from '../services/importJobService';
import { useCancelImportJob, useImportJobStatus } from '../hooks/useImportJobs';
import type { ImportJob } from '../types/importJob.types';
import { toast } from 'sonner';

const JOB_TYPE_LABELS: Record<string, string> = {
  order_import: 'Order Import',
  order_tracking_import: 'Order Tracking Import',
  product_import: 'Product Import',
  stock_import: 'Stock Import',
  spo_import: 'SPO Import',
  attachment_bulk_import: 'Attachment Bulk Import',
  grn_listing_import: 'Upload GRN',
  grn_lines_import: 'Upload GRN Lines',
};

function getJobTypeLabel(jobType: string): string {
  return JOB_TYPE_LABELS[jobType] ?? jobType;
}

type ImportJobDetailPageProps = {
  params: Promise<{ id: string }>;
};

export default function ImportJobDetailPage({ params }: ImportJobDetailPageProps) {
  const { id } = use(params);
  const router = useRouter();
  const searchParams = useSearchParams();
  const pageParam = searchParams.get('page');
  const pageSizeParam = searchParams.get('pageSize');
  const pageIndex = pageParam ? Math.max(0, parseInt(pageParam, 10) - 1) : null;
  const pageSize = pageSizeParam ? Math.max(1, parseInt(pageSizeParam, 10)) : 50;

  const { data: job, isLoading } = useQuery({
    queryKey: ['import-job', id],
    queryFn: () => getImportJob(id),
    staleTime: 1000 * 30,
    refetchOnWindowFocus: true,
    retry: 1,
  });

  const { data: jobsListData } = useQuery({
    queryKey: ['import-jobs', pageIndex ?? 0, pageSize],
    queryFn: () => getImportJobs({ pageIndex: pageIndex ?? 0, pageSize, sorting: [] }),
    enabled: pageIndex !== null && !!job,
  });

  const jobIds = jobsListData?.data?.map((j) => j.job_id) ?? [];
  const currentIndex = jobIds.indexOf(id);
  const hasPrev = currentIndex > 0;
  const hasNext = currentIndex >= 0 && currentIndex < jobIds.length - 1;
  const prevId = hasPrev ? jobIds[currentIndex - 1] : null;
  const nextId = hasNext ? jobIds[currentIndex + 1] : null;
  const totalOnPage = jobIds.length;
  const showPagination = pageIndex !== null && totalOnPage > 0 && currentIndex >= 0;

  // Poll for status updates if job is still processing
  const { data: statusData } = useImportJobStatus(id, !isLoading && !!job);
  const cancelJobMutation = useCancelImportJob();

  if (isLoading) {
    return (
      <>
        <Container>
          <Toolbar>
            <ToolbarHeading>
              <ToolbarTitle>Import Job</ToolbarTitle>
              <Breadcrumb>
                <BreadcrumbList>
                  <BreadcrumbItem>
                    <BreadcrumbLink href="/">Home</BreadcrumbLink>
                  </BreadcrumbItem>
                  <BreadcrumbSeparator />
                  <BreadcrumbItem>
                    <BreadcrumbPage>System Management</BreadcrumbPage>
                  </BreadcrumbItem>
                  <BreadcrumbSeparator />
                  <BreadcrumbItem>
                    <BreadcrumbLink href="/system-management/import-jobs">Import Jobs</BreadcrumbLink>
                  </BreadcrumbItem>
                </BreadcrumbList>
              </Breadcrumb>
            </ToolbarHeading>
            <ToolbarActions>
              <Button asChild variant="outline">
                <Link href="/system-management/import-jobs">
                  <MoveLeft /> Back to Import Jobs
                </Link>
              </Button>
            </ToolbarActions>
          </Toolbar>
        </Container>
        <Container>
          <div className="space-y-6">
            <Skeleton className="h-10 w-64" />
            <Skeleton className="h-96 w-full" />
          </div>
        </Container>
      </>
    );
  }

  if (!job) {
    return (
      <>
        <Container>
          <Toolbar>
            <ToolbarHeading>
              <ToolbarTitle>Import Job</ToolbarTitle>
              <Breadcrumb>
                <BreadcrumbList>
                  <BreadcrumbItem>
                    <BreadcrumbLink href="/">Home</BreadcrumbLink>
                  </BreadcrumbItem>
                  <BreadcrumbSeparator />
                  <BreadcrumbItem>
                    <BreadcrumbPage>System Management</BreadcrumbPage>
                  </BreadcrumbItem>
                  <BreadcrumbSeparator />
                  <BreadcrumbItem>
                    <BreadcrumbLink href="/system-management/import-jobs">Import Jobs</BreadcrumbLink>
                  </BreadcrumbItem>
                </BreadcrumbList>
              </Breadcrumb>
            </ToolbarHeading>
            <ToolbarActions>
              <Button asChild variant="outline">
                <Link href="/system-management/import-jobs">
                  <MoveLeft /> Back to Import Jobs
                </Link>
              </Button>
            </ToolbarActions>
          </Toolbar>
        </Container>
        <Container>
          <div className="text-center py-12">
            <p className="text-muted-foreground">Import job not found</p>
            <Button variant="outline" onClick={() => router.push('/system-management/import-jobs')} className="mt-4">
              Back to Import Jobs
            </Button>
          </div>
        </Container>
      </>
    );
  }

  const progress = statusData?.progress;
  const progressPercentage = progress ? progress.percentage : (job.total_rows > 0 ? Math.round((job.processed_rows / job.total_rows) * 100) : 0);
  const currentStatus = statusData?.status || job.status;
  const canCancel = ['pending', 'queued', 'started'].includes(currentStatus);

  // Use statusData.progress when available (polled every 2s) so Processed/Success/Failed/Skipped stay in sync
  const displayProcessed = progress ? progress.processed : job.processed_rows;
  const displaySuccessful = progress ? progress.successful : job.successful_rows;
  const displayFailed = progress ? progress.failed : job.failed_rows;
  const displaySkipped = progress ? progress.skipped : job.skipped_rows;

  return (
    <>
      <Container>
        <Toolbar>
          <ToolbarHeading>
            <ToolbarTitle>Import Job Details</ToolbarTitle>
            <Breadcrumb>
              <BreadcrumbList>
                <BreadcrumbItem>
                  <BreadcrumbLink href="/">Home</BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbPage>System Management</BreadcrumbPage>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbLink href="/system-management/import-jobs">Import Jobs</BreadcrumbLink>
                </BreadcrumbItem>
              </BreadcrumbList>
            </Breadcrumb>
          </ToolbarHeading>
          <ToolbarActions>
            {showPagination && (
              <div className="flex items-center gap-1 mr-2">
                <Button
                  variant="outline"
                  size="icon"
                  className="h-8 w-8"
                  disabled={!hasPrev}
                  asChild={!!prevId}
                >
                  {prevId ? (
                    <Link href={`/system-management/import-jobs/${prevId}?page=${(pageIndex ?? 0) + 1}&pageSize=${pageSize}`}>
                      <ChevronLeft className="size-4" />
                    </Link>
                  ) : (
                    <span><ChevronLeft className="size-4" /></span>
                  )}
                </Button>
                <span className="text-sm text-muted-foreground tabular-nums px-1 min-w-[4rem] text-center">
                  {currentIndex + 1} / {totalOnPage}
                </span>
                <Button
                  variant="outline"
                  size="icon"
                  className="h-8 w-8"
                  disabled={!hasNext}
                  asChild={!!nextId}
                >
                  {nextId ? (
                    <Link href={`/system-management/import-jobs/${nextId}?page=${(pageIndex ?? 0) + 1}&pageSize=${pageSize}`}>
                      <ChevronRight className="size-4" />
                    </Link>
                  ) : (
                    <span><ChevronRight className="size-4" /></span>
                  )}
                </Button>
              </div>
            )}
            <Button asChild variant="outline">
              <Link href={pageIndex !== null ? `/system-management/import-jobs?page=${pageIndex + 1}&pageSize=${pageSize}` : '/system-management/import-jobs'}>
                <MoveLeft /> Back to Import Jobs
              </Link>
            </Button>
            {canCancel && (
              <Button
                variant="outline"
                disabled={cancelJobMutation.isPending}
                onClick={() => {
                  cancelJobMutation.mutate(id, {
                    onSuccess: (data) => {
                      toast.success(data.message || 'Job cancelled');
                    },
                    onError: (error) => {
                      toast.error(error instanceof Error ? error.message : 'Failed to cancel job');
                    },
                  });
                }}
              >
                {cancelJobMutation.isPending ? 'Cancelling...' : 'Cancel Job'}
              </Button>
            )}
          </ToolbarActions>
        </Toolbar>
      </Container>

      <Container>
        <div className="space-y-6">
          {/* Summary Card */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Job Summary</CardTitle>
                <Badge variant={getStatusBadgeVariant(statusData?.status || job.status)}>
                  {(statusData?.status || job.status || '').toUpperCase()}
                </Badge>
              </div>
            </CardHeader>
            <CardContent>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 text-sm">
                <div>
                  <p className="text-muted-foreground">Job Type</p>
                  <p className="font-medium">{getJobTypeLabel(job.job_type)}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Status</p>
                  <p className="font-medium">
                    <Badge variant={getStatusBadgeVariant(statusData?.status || job.status)}>
                      {(statusData?.status || job.status || '').toUpperCase()}
                    </Badge>
                  </p>
                </div>
                <div>
                  <p className="text-muted-foreground">Total Rows</p>
                  <p className="font-medium text-lg">{job.total_rows}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Processed</p>
                  <p className="font-medium text-lg">{displayProcessed} / {job.total_rows}</p>
                </div>
                {job.filename && (
                  <div>
                    <p className="text-muted-foreground">Filename</p>
                    <p className="font-medium">{job.filename}</p>
                  </div>
                )}
                {job.has_source_file && (
                  <div>
                    <p className="text-muted-foreground">Source File</p>
                    <Button
                      variant="outline"
                      size="sm"
                      className="mt-1"
                      onClick={async () => {
                        try {
                          const blob = await downloadImportJobSourceFile(id);
                          const objectUrl = window.URL.createObjectURL(blob);
                          const a = document.createElement('a');
                          a.href = objectUrl;
                          a.download = job.source_filename || job.filename || 'import-source.xlsx';
                          document.body.appendChild(a);
                          a.click();
                          window.URL.revokeObjectURL(objectUrl);
                          document.body.removeChild(a);
                        } catch {
                          toast.error('Could not download the original uploaded file.');
                        }
                      }}
                    >
                      <Download className="size-4" />
                      Download original
                    </Button>
                  </div>
                )}
                <div>
                  <p className="text-muted-foreground">Created At</p>
                  <p className="font-medium">{formatDateTimeInMalaysia(job.created_at)}</p>
                </div>
                {job.started_at && (
                  <div>
                    <p className="text-muted-foreground">Started At</p>
                    <p className="font-medium">{formatDateTimeInMalaysia(job.started_at)}</p>
                  </div>
                )}
                {job.completed_at && (
                  <div>
                    <p className="text-muted-foreground">Completed At</p>
                    <p className="font-medium">{formatDateTimeInMalaysia(job.completed_at)}</p>
                  </div>
                )}
              </div>

              {/* Progress Bar - show when we have total from progress (polled) or job */}
              {(progress?.total ?? job.total_rows) > 0 && ['pending', 'queued', 'started'].includes(currentStatus) && (
                <div className="mt-6 space-y-2">
                  <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">Progress</span>
                    <span className="font-medium">{progressPercentage}%</span>
                  </div>
                  <Progress value={progressPercentage} />
                </div>
              )}
            </CardContent>
          </Card>

          {(statusData?.error || job.error) && (
            <Card>
              <CardHeader>
                <CardTitle>Error</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-destructive whitespace-pre-wrap">
                  {statusData?.error || job.error}
                </p>
              </CardContent>
            </Card>
          )}

          {/* Results Card */}
          <Card>
            <CardHeader>
              <CardTitle>Results</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 text-sm">
                <div>
                  <p className="text-muted-foreground">Successful</p>
                  <p className="font-medium text-lg text-emerald-600">{displaySuccessful}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Failed</p>
                  <p className="font-medium text-lg text-red-600">{displayFailed}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Skipped</p>
                  <p className="font-medium text-lg text-yellow-600">{displaySkipped}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Processed</p>
                  <p className="font-medium text-lg">{displayProcessed}</p>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Error Card */}
          {job.error && (
            <Card>
              <CardHeader>
                <CardTitle className="text-red-600">Error</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-red-700 dark:text-red-400">{job.error}</p>
              </CardContent>
            </Card>
          )}

          {/* Result Details (if available) */}
          {job.result && typeof job.result === 'object' && Object.keys(job.result).length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Result Details</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {(typeof job.result.allocations_created === 'number' ||
                  typeof job.result.allocations_updated === 'number') && (
                  <div className="flex flex-wrap gap-2 text-sm">
                    {typeof job.result.allocations_created === 'number' && (
                      <span className="rounded bg-emerald-50 dark:bg-emerald-950/30 text-emerald-700 dark:text-emerald-400 px-2 py-1">
                        Allocations created: {job.result.allocations_created}
                      </span>
                    )}
                    {typeof job.result.allocations_updated === 'number' && (
                      <span className="rounded bg-sky-50 dark:bg-sky-950/30 text-sky-700 dark:text-sky-400 px-2 py-1">
                        Allocations updated: {job.result.allocations_updated}
                      </span>
                    )}
                  </div>
                )}
                {Array.isArray(job.result.successful_rows_detail) && job.result.successful_rows_detail.length > 0 && (
                  <div>
                    <p className="text-sm font-medium text-emerald-600 dark:text-emerald-400 mb-2">
                      Successful lines ({job.result.successful_rows_detail.length})
                    </p>
                    <ul className="text-sm space-y-1 max-h-60 overflow-y-auto bg-emerald-50 dark:bg-emerald-950/30 p-3 rounded">
                      {job.result.successful_rows_detail.map(
                        (
                          entry: {
                            grn_number?: string;
                            product_code?: string;
                            warehouse?: string;
                            quantity?: number;
                          },
                          i: number
                        ) => (
                          <li key={i} className="flex gap-2 flex-wrap">
                            <span className="font-mono shrink-0">
                              {entry.grn_number ?? '—'}
                            </span>
                            <span className="text-muted-foreground">·</span>
                            <span>{entry.product_code ?? '—'}</span>
                            <span className="text-muted-foreground">·</span>
                            <span>{entry.warehouse ?? '—'}</span>
                            <span className="text-muted-foreground">·</span>
                            <span>Qty {entry.quantity ?? '—'}</span>
                          </li>
                        )
                      )}
                    </ul>
                  </div>
                )}
                {Array.isArray(job.result.warnings) && job.result.warnings.length > 0 && (
                  <div>
                    <p className="text-sm font-medium text-amber-600 dark:text-amber-500 mb-2">
                      Warnings ({job.result.warnings.length})
                    </p>
                    <ul className="text-sm space-y-1 max-h-60 overflow-y-auto bg-muted/50 p-3 rounded list-disc pl-6 text-amber-600 dark:text-amber-500">
                      {/* Warnings are plain strings for most importers, but the
                          order-tracking import emits {row, warning, data} objects —
                          rendering an object as a React child crashes the page. */}
                      {(job.result.warnings as unknown[]).map((w, i: number) => {
                        if (typeof w === 'string') return <li key={i}>{w}</li>;
                        const obj = (w ?? {}) as { row?: number; warning?: string };
                        const text =
                          obj.warning ??
                          (typeof w === 'object' ? JSON.stringify(w) : String(w));
                        return (
                          <li key={i}>
                            {obj.row != null ? `Row ${obj.row}: ` : ''}
                            {text}
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                )}
                {Array.isArray(job.result.skipped_rows_detail) && job.result.skipped_rows_detail.length > 0 && (
                  <div>
                    <p className="text-sm font-medium text-muted-foreground mb-2">
                      Skipped rows ({job.result.skipped_rows_detail.length})
                    </p>
                    <ul className="text-sm space-y-1 max-h-60 overflow-y-auto bg-muted/50 p-3 rounded">
                      {job.result.skipped_rows_detail.map((entry: { row?: number; reason?: string }, i: number) => (
                        <li key={i} className="flex gap-2">
                          <span className="font-mono text-muted-foreground shrink-0">Row {entry.row ?? i + 1}:</span>
                          <span>{entry.reason ?? 'Unknown'}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                <details className="text-sm">
                  <summary className="cursor-pointer text-muted-foreground hover:text-foreground">Full result (JSON)</summary>
                  <pre className="text-xs bg-muted p-4 rounded overflow-auto mt-2">
                    {JSON.stringify(job.result, null, 2)}
                  </pre>
                </details>
              </CardContent>
            </Card>
          )}
        </div>
      </Container>
    </>
  );
}
