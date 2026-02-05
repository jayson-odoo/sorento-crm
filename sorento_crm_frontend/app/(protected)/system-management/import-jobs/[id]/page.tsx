'use client';

import { use } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { MoveLeft } from 'lucide-react';
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
import { formatDateTime } from '@/lib/helpers';
import { getImportJob, getImportJobStatus } from '../services/importJobService';
import { useImportJobStatus } from '../hooks/useImportJobs';
import type { ImportJob } from '../types/importJob.types';

type ImportJobDetailPageProps = {
  params: Promise<{ id: string }>;
};

export default function ImportJobDetailPage({ params }: ImportJobDetailPageProps) {
  const { id } = use(params);
  const router = useRouter();

  const { data: job, isLoading } = useQuery({
    queryKey: ['import-job', id],
    queryFn: () => getImportJob(id),
    staleTime: 1000 * 30,
    refetchOnWindowFocus: true,
    retry: 1,
  });

  // Poll for status updates if job is still processing
  const { data: statusData } = useImportJobStatus(id, !isLoading && !!job);

  const getStatusBadge = (status: string) => {
    const variants: Record<string, { variant: 'primary' | 'secondary' | 'destructive' | 'outline'; appearance?: 'ghost' }> = {
      pending: { variant: 'outline' },
      queued: { variant: 'secondary' },
      started: { variant: 'secondary', appearance: 'ghost' },
      finished: { variant: 'primary' },
      failed: { variant: 'destructive' },
      cancelled: { variant: 'outline' },
    };
    const config = variants[status] || { variant: 'secondary' };
    return <Badge {...config}>{status.toUpperCase()}</Badge>;
  };

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
          {/* Summary Card */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Job Summary</CardTitle>
                {getStatusBadge(statusData?.status || job.status)}
              </div>
            </CardHeader>
            <CardContent>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 text-sm">
                <div>
                  <p className="text-muted-foreground">Job Type</p>
                  <p className="font-medium">{job.job_type}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Status</p>
                  <p className="font-medium">{getStatusBadge(statusData?.status || job.status)}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Total Rows</p>
                  <p className="font-medium text-lg">{job.total_rows}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Processed</p>
                  <p className="font-medium text-lg">{job.processed_rows} / {job.total_rows}</p>
                </div>
                {job.filename && (
                  <div>
                    <p className="text-muted-foreground">Filename</p>
                    <p className="font-medium">{job.filename}</p>
                  </div>
                )}
                <div>
                  <p className="text-muted-foreground">Created At</p>
                  <p className="font-medium">{formatDateTime(new Date(job.created_at))}</p>
                </div>
                {job.started_at && (
                  <div>
                    <p className="text-muted-foreground">Started At</p>
                    <p className="font-medium">{formatDateTime(new Date(job.started_at))}</p>
                  </div>
                )}
                {job.completed_at && (
                  <div>
                    <p className="text-muted-foreground">Completed At</p>
                    <p className="font-medium">{formatDateTime(new Date(job.completed_at))}</p>
                  </div>
                )}
              </div>

              {/* Progress Bar */}
              {job.total_rows > 0 && ['pending', 'queued', 'started'].includes(job.status) && (
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

          {/* Results Card */}
          <Card>
            <CardHeader>
              <CardTitle>Results</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 text-sm">
                <div>
                  <p className="text-muted-foreground">Successful</p>
                  <p className="font-medium text-lg text-emerald-600">{job.successful_rows}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Failed</p>
                  <p className="font-medium text-lg text-red-600">{job.failed_rows}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Skipped</p>
                  <p className="font-medium text-lg text-yellow-600">{job.skipped_rows}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Processed</p>
                  <p className="font-medium text-lg">{job.processed_rows}</p>
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

          {/* Result JSON (if available) */}
          {job.result && typeof job.result === 'object' && Object.keys(job.result).length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Result Details</CardTitle>
              </CardHeader>
              <CardContent>
                <pre className="text-xs bg-muted p-4 rounded overflow-auto">
                  {JSON.stringify(job.result, null, 2)}
                </pre>
              </CardContent>
            </Card>
          )}
        </div>
      </Container>
    </>
  );
}
