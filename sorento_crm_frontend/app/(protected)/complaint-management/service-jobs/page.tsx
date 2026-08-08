'use client';

/**
 * Every service job, findable without knowing which day it is on.
 *
 * The dispatch board answers "who is working today". That is the right question at 8am and
 * the wrong one every other time: it filters on a single day's `scheduled_from`, so a job
 * proposed with no date yet - the state every job starts in - is on no day at all, and a
 * job confirmed for last Tuesday leaves the board the moment it moves on. Raise a job, look
 * for it tomorrow, and it has vanished. This list is where it lives.
 */

import { useState } from 'react';
import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { CalendarRange } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
import { formatDateTimeInMalaysia } from '@/lib/helpers';

import {
  SERVICE_JOB_STATUS_LABELS,
  formatDuration,
  listServiceJobs,
  type ServiceJobStatusKey,
} from './services/serviceJobService';

const STATUS_OPTIONS = [
  { value: '', label: 'Any status' },
  ...Object.entries(SERVICE_JOB_STATUS_LABELS).map(([value, label]) => ({ value, label })),
];

export default function ServiceJobsPage() {
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');

  const jobs = useQuery({
    queryKey: ['service-jobs-list', search, status],
    queryFn: () =>
      listServiceJobs({
        query: search.trim() || undefined,
        status: status ? [status] : undefined,
        limit: 100,
      }),
  });

  const rows = jobs.data?.data ?? [];

  return (
    <div className="flex flex-col gap-4 p-4 sm:p-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="min-w-0 text-xl font-semibold break-words">Service Jobs</h1>
        <Button variant="outline" asChild className="shrink-0">
          <Link href="/complaint-management/service-jobs/board">
            <CalendarRange className="mr-1.5 size-4" />
            Dispatch board
          </Link>
        </Button>
      </div>

      <div className="flex flex-col gap-2 sm:flex-row">
        <Input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search job number, site or contact"
          className="sm:max-w-sm"
        />
        <div className="sm:w-52">
          <SearchableSelect
            value={status}
            onChange={setStatus}
            options={STATUS_OPTIONS}
            placeholder="Any status"
          />
        </div>
      </div>

      <Card>
        <CardContent className="p-0">
          {jobs.isLoading ? (
            <div className="p-4">
              <Skeleton className="h-24 w-full" />
            </div>
          ) : jobs.isError ? (
            <p className="p-8 text-center text-sm text-muted-foreground">
              {(jobs.error as Error)?.message ?? 'Failed to load service jobs.'}
            </p>
          ) : rows.length === 0 ? (
            // Jobs are raised FROM a case, never here, so there is no Add button to offer:
            // pointing at one that does not exist is worse than saying nothing.
            <p className="p-8 text-center text-sm text-muted-foreground">
              {search || status ? 'No service jobs match.' : 'No service jobs yet.'}
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground">
                  <tr>
                    <th className="px-4 py-2 text-left">Job</th>
                    <th className="px-4 py-2 text-left">Site</th>
                    <th className="px-4 py-2 text-left">Scheduled</th>
                    <th className="px-4 py-2 text-left">Attended in</th>
                    <th className="px-4 py-2 text-left">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((job) => (
                    <tr key={job.id} className="border-t hover:bg-accent/50">
                      <td className="px-4 py-2 font-medium">
                        <Link
                          href={`/complaint-management/service-jobs/${job.id}`}
                          className="text-primary hover:underline"
                        >
                          {job.job_number ?? 'Unnumbered'}
                        </Link>
                      </td>
                      <td
                        className="max-w-xs truncate px-4 py-2"
                        title={job.site_address ?? ''}
                      >
                        {job.site_address ?? '-'}
                      </td>
                      <td className="px-4 py-2">
                        {job.scheduled_from ? (
                          formatDateTimeInMalaysia(job.scheduled_from)
                        ) : (
                          // The commonest state, and not a gap in the data: nobody has
                          // agreed a time yet, which is exactly what Proposed means.
                          <span className="text-muted-foreground">Not scheduled</span>
                        )}
                      </td>
                      <td className="px-4 py-2 text-muted-foreground">
                        {job.attend_seconds !== null ? formatDuration(job.attend_seconds) : '-'}
                      </td>
                      <td className="px-4 py-2">
                        <span
                          className={`${STATUS_PILL_BASE} ${statusPillClass(job.status_key)}`}
                        >
                          {job.status_key
                            ? SERVICE_JOB_STATUS_LABELS[job.status_key as ServiceJobStatusKey]
                            : 'Unknown'}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
