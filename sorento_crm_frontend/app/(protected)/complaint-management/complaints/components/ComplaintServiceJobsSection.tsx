'use client';

import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { useComplaintServiceJobs } from '../../service-jobs/hooks/useServiceJobs';
import ServiceJobStatusPill from '../../service-jobs/components/ServiceJobStatusPill';

export default function ComplaintServiceJobsSection({ complaintId }: { complaintId: string }) {
  const { data: jobs = [], isLoading } = useComplaintServiceJobs(complaintId);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Service Jobs</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? null : jobs.length === 0 ? (
          <div className="py-2">
            <p className="font-medium">No service jobs yet</p>
            <p className="text-sm text-muted-foreground">
              A job appears here when a technician is sent to the site.
            </p>
          </div>
        ) : (
          <ul className="divide-y">
            {jobs.map((job) => (
              <li key={job.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 py-2 text-sm">
                <Link
                  href={`/complaint-management/service-jobs/${job.id}`}
                  className="font-medium text-primary hover:underline"
                >
                  {job.job_number}
                </Link>
                <ServiceJobStatusPill status={job.status} label={job.status_label} />
                <span className="truncate text-muted-foreground">
                  {job.scheduled_from ? formatDateTimeInMalaysia(job.scheduled_from) : '-'}
                </span>
                <span className="truncate">{job.technician_name || '-'}</span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
