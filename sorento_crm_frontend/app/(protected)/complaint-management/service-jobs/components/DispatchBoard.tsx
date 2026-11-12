'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DatePicker } from '@/components/ui/date-picker';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDateTimeInMalaysia, todayMalaysiaYyyyMmDd } from '@/lib/helpers';
import { useDispatchBoard } from '../hooks/useServiceJobs';
import { ymd } from '../lib/jobDates';
import type { ServiceJob } from '../types/serviceJob.types';
import ServiceJobStatusPill from './ServiceJobStatusPill';

function parseYmd(value: string): Date {
  const [y, m, d] = value.split('-').map(Number);
  return new Date(y, m - 1, d);
}

function timeOf(job: ServiceJob): string {
  if (!job.scheduled_from) return '-';
  const text = formatDateTimeInMalaysia(job.scheduled_from);
  return text.includes(',') ? text.split(',').slice(1).join(',').trim() : text;
}

function JobCard({ job, withDate }: { job: ServiceJob; withDate?: boolean }) {
  return (
    <Link
      href={`/complaint-management/service-jobs/${job.id}`}
      className="block rounded-md border p-2 text-sm hover:bg-muted/40"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="truncate font-medium">{job.job_number}</span>
        <ServiceJobStatusPill status={job.status} label={job.status_label} />
      </div>
      <div className="mt-1 flex items-center justify-between gap-2 text-muted-foreground">
        <span className="truncate">
          {withDate && job.scheduled_from ? formatDateTimeInMalaysia(job.scheduled_from) : timeOf(job)}
        </span>
        <span className="truncate">{job.city || '-'}</span>
      </div>
    </Link>
  );
}

export default function DispatchBoard() {
  const [day, setDay] = useState(() => todayMalaysiaYyyyMmDd());
  const { data, isLoading } = useDispatchBoard(day);

  const shift = (days: number) => {
    const d = parseYmd(day);
    d.setDate(d.getDate() + days);
    setDay(ymd(d));
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" onClick={() => shift(-1)}>
          Previous
        </Button>
        <DatePicker
          className="w-48"
          required
          ariaLabel="Day"
          value={parseYmd(day)}
          onChange={(d) => d && setDay(ymd(d))}
        />
        <Button variant="outline" onClick={() => shift(1)}>
          Next
        </Button>
        <Button variant="outline" onClick={() => setDay(todayMalaysiaYyyyMmDd())}>
          Today
        </Button>
      </div>

      {isLoading || !data ? (
        <Skeleton className="h-64 w-full" />
      ) : (
        <>
          {data.stalled.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Stalled jobs</CardTitle>
              </CardHeader>
              <CardContent className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {data.stalled.map((job) => (
                  <JobCard key={job.id} job={job} withDate />
                ))}
              </CardContent>
            </Card>
          )}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {data.columns.map((col) => (
              <Card key={col.technician_id ?? 'unassigned'}>
                <CardHeader>
                  <CardTitle className="truncate">{col.technician_name}</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  {col.jobs.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No jobs</p>
                  ) : (
                    col.jobs.map((job) => <JobCard key={job.id} job={job} />)
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
