'use client';

/**
 * The link between a complaint and somebody actually going to the site.
 *
 * Before this section the dispatch board had no door: jobs existed only if something called
 * the API directly. This is where CS decides a visit is needed, and it is on the complaint
 * because that is where they already are when they decide it.
 *
 * **The button sends the case id and nothing else.** The Site is copied server-side from what
 * the complaint REPORTED (AC-B3), never from what this page happens to be displaying. A
 * complaint routinely carries the dealer's shop in `customer_address` alongside the house the
 * fault is in; posting the wrong one from here would send a van to a shop, and both are real
 * addresses so nothing would look wrong.
 *
 * **The list renders before the button matters.** A revisit is a legitimate second job, so
 * raising is not blocked - but showing what already exists is the only guard against somebody
 * raising a third one because they could not see the first two.
 *
 * Always rendered, empty or not, per the CRUD standard: "no service jobs" plus the next step
 * is information, and a section that vanishes on missing data teaches people it is not there.
 */

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Truck } from 'lucide-react';
import { toast } from 'sonner';

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
import { formatDateTimeInMalaysia } from '@/lib/helpers';

import {
  SERVICE_JOB_STATUS_LABELS,
  formatDuration,
  getJobsForSource,
  raiseServiceJobFromSource,
  type ServiceJob,
} from '../../service-jobs/services/serviceJobService';

export interface ComplaintServiceJobsSectionProps {
  complaintId: string;
}

export default function ComplaintServiceJobsSection({
  complaintId,
}: ComplaintServiceJobsSectionProps) {
  const queryClient = useQueryClient();
  const [confirmOpen, setConfirmOpen] = useState(false);

  const jobs = useQuery({
    queryKey: ['complaint-service-jobs', complaintId],
    queryFn: () => getJobsForSource('complaint', complaintId),
  });

  const raise = useMutation({
    mutationFn: () => raiseServiceJobFromSource('complaint', complaintId),
    onSuccess: (job: ServiceJob) => {
      toast.success(
        job.job_number
          ? `Service job ${job.job_number} raised. Confirm a date on the dispatch board.`
          : 'Service job raised. Confirm a date on the dispatch board.',
      );
      setConfirmOpen(false);
      queryClient.invalidateQueries({ queryKey: ['complaint-service-jobs', complaintId] });
      queryClient.invalidateQueries({ queryKey: ['service-job-board'] });
      queryClient.invalidateQueries({ queryKey: ['service-job-stalls'] });
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const rows = useMemo(() => jobs.data ?? [], [jobs.data]);

  return (
    <>
      <Card>
        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <CardTitle className="flex items-center gap-2">
              <Truck className="size-4" />
              Service Jobs
              <Badge variant="secondary">{rows.length}</Badge>
            </CardTitle>
            <p className="mt-1 text-xs text-muted-foreground">
              Somebody going to the site. The site is taken from what this complaint reported,
              not from the customer record.
            </p>
          </div>
          <Button
            className="shrink-0"
            variant={rows.length === 0 ? 'primary' : 'outline'}
            onClick={() => setConfirmOpen(true)}
            disabled={raise.isPending}
          >
            Raise service job
          </Button>
        </CardHeader>
        <CardContent>
          {jobs.isLoading ? (
            <Skeleton className="h-20 w-full" />
          ) : jobs.isError ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              {(jobs.error as Error)?.message ?? 'Failed to load service jobs.'}
            </p>
          ) : rows.length === 0 ? (
            <div className="py-6 text-center">
              <p className="text-sm text-muted-foreground">
                No service job yet. Nobody has been sent to this site.
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                Raising one puts it on the{' '}
                <Link className="underline" href="/complaint-management/service-jobs">
                  dispatch board
                </Link>{' '}
                as proposed, waiting for a date the customer agrees to.
              </p>
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              {rows.map((job) => (
                <Link
                  key={job.id}
                  href="/complaint-management/service-jobs"
                  className="flex flex-col gap-1 rounded-md border p-3 transition-colors hover:bg-accent sm:flex-row sm:items-center sm:justify-between"
                >
                  <span className="flex min-w-0 flex-col">
                    <span className="text-sm font-medium">
                      {job.job_number ?? 'Unnumbered'}
                    </span>
                    <span className="truncate text-xs text-muted-foreground">
                      {job.site_address ?? 'No site recorded'}
                    </span>
                  </span>
                  <span className="flex shrink-0 flex-wrap items-center gap-2">
                    {job.scheduled_from && (
                      <span className="text-xs text-muted-foreground">
                        {formatDateTimeInMalaysia(job.scheduled_from)}
                      </span>
                    )}
                    {job.attend_seconds !== null && (
                      <span className="text-xs text-muted-foreground">
                        attended in {formatDuration(job.attend_seconds)}
                      </span>
                    )}
                    <span className={`${STATUS_PILL_BASE} ${statusPillClass(job.status_key)}`}>
                      {job.status_key ? SERVICE_JOB_STATUS_LABELS[job.status_key] : 'Unknown'}
                    </span>
                  </span>
                </Link>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Confirmed rather than one-click: raising commits the office to sending somebody,
          and a second job on a case that already has one reads as a revisit in every
          report that counts them. */}
      <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Raise a service job?</AlertDialogTitle>
            <AlertDialogDescription>
              {rows.length === 0
                ? 'This puts a proposed job on the dispatch board. It is not scheduled until somebody confirms a date the customer has agreed to.'
                : `This complaint already has ${rows.length} service job${rows.length === 1 ? '' : 's'}. A new one is recorded as a separate visit, which is what a revisit is.`}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => raise.mutate()}>Raise job</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
