'use client';

/**
 * The dispatch board - a day, and the people working it.
 *
 * Deliberately what a dispatcher already draws on paper: no availability grid, no skills
 * matrix, no geo-clustering, no capacity optimiser. Every one of those needs data Sorento
 * does not collect, and would produce confident schedules out of guesses.
 *
 * **Unassigned is the first column, always rendered.** A confirmed job nobody is going to is
 * the single most important thing on this screen, and a board that only shows technicians
 * groups it out of existence - which is exactly how it gets missed until the consumer calls.
 * It renders even when empty, per the CRUD standard's "always render every section".
 *
 * **Stalls sit above the board, not inside it.** A job past its date and still Proposed has
 * nobody behind it and no column to belong to; putting it in a technician's day would imply
 * somebody is handling it. A CONFIRMED job past its date is deliberately NOT a stall - it has
 * an agreed date and an accountable technician, and listing it would bury the real ones.
 */

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, ChevronLeft, ChevronRight } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';

import { ServiceJobPanel } from '../components/ServiceJobPanel';
import {
  SERVICE_JOB_STATUS_LABELS,
  formatDuration,
  getDispatchBoard,
  getServiceJob,
  getStalledJobs,
  listTechnicians,
  type BoardGroup,
  type BoardJob,
} from '../services/serviceJobService';

function toDayString(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function shiftDay(day: string, delta: number): string {
  const date = new Date(`${day}T00:00:00`);
  date.setDate(date.getDate() + delta);
  return toDayString(date);
}

function timeOf(iso: string | null): string {
  if (!iso) return '';
  const date = new Date(iso);
  return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
}

function JobCard({ job, onOpen }: { job: BoardJob; onOpen: (id: string) => void }) {
  return (
    <button
      type="button"
      onClick={() => onOpen(job.service_job_id)}
      className="w-full rounded-md border p-3 text-left transition-colors hover:bg-accent"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="truncate text-sm font-medium" title={job.job_number ?? ''}>
          {job.job_number ?? 'Unnumbered'}
        </span>
        <span className="shrink-0 text-xs text-muted-foreground">
          {timeOf(job.scheduled_from)}
        </span>
      </div>
      <div className="mt-1 truncate text-xs text-muted-foreground" title={job.site_address ?? ''}>
        {job.site_address ?? 'No site recorded'}
      </div>
      <div className="mt-2">
        <span className={`${STATUS_PILL_BASE} ${statusPillClass(job.status_key)}`}>
          {job.status_key ? SERVICE_JOB_STATUS_LABELS[job.status_key] : 'Unknown'}
        </span>
      </div>
    </button>
  );
}

function BoardColumn({
  title,
  jobs,
  onOpen,
}: {
  title: string;
  jobs: BoardJob[];
  onOpen: (id: string) => void;
}) {
  return (
    <Card className="flex min-w-[260px] flex-1 flex-col">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center justify-between gap-2 text-sm">
          <span className="truncate" title={title}>
            {title}
          </span>
          <Badge variant="secondary">{jobs.length}</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        {jobs.length === 0 ? (
          <p className="py-6 text-center text-xs text-muted-foreground">None.</p>
        ) : (
          jobs.map((job) => <JobCard key={job.service_job_id} job={job} onOpen={onOpen} />)
        )}
      </CardContent>
    </Card>
  );
}

export default function DispatchBoardPage() {
  const [day, setDay] = useState(() => toDayString(new Date()));
  const [openJobId, setOpenJobId] = useState<string | null>(null);

  const board = useQuery({
    queryKey: ['service-job-board', day],
    queryFn: () =>
      getDispatchBoard({ dateFrom: `${day}T00:00:00`, dateTo: `${shiftDay(day, 1)}T00:00:00` }),
  });

  const stalls = useQuery({
    queryKey: ['service-job-stalls'],
    queryFn: getStalledJobs,
  });

  const technicians = useQuery({
    queryKey: ['service-job-technicians'],
    queryFn: () => listTechnicians({ isActive: true }),
  });

  const selected = useQuery({
    queryKey: ['service-job', openJobId],
    queryFn: () => getServiceJob(openJobId as string),
    enabled: Boolean(openJobId),
  });

  const groups: BoardGroup[] = board.data ?? [];
  const unassigned = useMemo(
    () => groups.filter((group) => group.technician_id === null).flatMap((group) => group.jobs),
    [groups],
  );
  const assigned = useMemo(
    () => groups.filter((group) => group.technician_id !== null),
    [groups],
  );

  return (
    <div className="flex flex-col gap-6 p-4 sm:p-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          {/* No explanatory subtitle. A screen that has to describe what it is has already
              failed, and the cursor rules put feature explanations in the docs, not the UI. */}
          <h1 className="text-xl font-semibold break-words">Dispatch board</h1>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" size="icon" onClick={() => setDay(shiftDay(day, -1))}>
            <ChevronLeft className="size-4" />
          </Button>
          <Input
            type="date"
            className="w-auto"
            value={day}
            onChange={(event) => setDay(event.target.value)}
          />
          <Button variant="outline" size="icon" onClick={() => setDay(shiftDay(day, 1))}>
            <ChevronRight className="size-4" />
          </Button>
          <Button variant="outline" onClick={() => setDay(toDayString(new Date()))}>
            Today
          </Button>
        </div>
      </div>

      {/* Always rendered, per the CRUD standard: an empty stall list is information. */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-sm">
            <AlertTriangle className="size-4 text-amber-600" />
            Stalled jobs
            <Badge variant="secondary">{stalls.data?.length ?? 0}</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {stalls.isLoading ? (
            <Skeleton className="h-16 w-full" />
          ) : (stalls.data?.length ?? 0) === 0 ? (
            <p className="py-4 text-center text-sm text-muted-foreground">No stalled jobs.</p>
          ) : (
            <div className="overflow-x-auto">
              <div className="flex flex-col gap-2">
                {stalls.data?.map((stall) => (
                  <button
                    key={stall.service_job_id}
                    type="button"
                    onClick={() => setOpenJobId(stall.service_job_id)}
                    className="flex flex-col gap-1 rounded-md border border-amber-200 bg-amber-50 p-3 text-left transition-colors hover:bg-amber-100 sm:flex-row sm:items-center sm:justify-between"
                  >
                    {/* Two blocks, not two inline spans: side by side the number and the
                        address run together into "SV26/08-00035 Lorong Bukit" for anything
                        reading the text rather than the margin - a screen reader, a test,
                        or a 375px screen. */}
                    <span className="flex min-w-0 flex-col">
                      <span className="text-sm font-medium">
                        {stall.job_number ?? 'Unnumbered'}
                      </span>
                      <span className="truncate text-xs text-muted-foreground">
                        {stall.site_address ?? 'No site recorded'}
                      </span>
                    </span>
                    <span className="shrink-0 text-xs font-medium text-amber-800">
                      stalled {formatDuration(stall.stalled_seconds)}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {board.isLoading ? (
        <div className="flex gap-4">
          <Skeleton className="h-64 flex-1" />
          <Skeleton className="h-64 flex-1" />
        </div>
      ) : board.isError ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            {(board.error as Error)?.message ?? 'Failed to load the board.'}
          </CardContent>
        </Card>
      ) : (
        <div className="flex flex-col gap-4 lg:flex-row lg:overflow-x-auto">
          {/* First and always present. See the module note. */}
          <BoardColumn
            title="Unassigned"
            jobs={unassigned}
            onOpen={setOpenJobId}
          />
          {assigned.map((group) => (
            <BoardColumn
              key={`${group.day}-${group.technician_id}`}
              title={group.technician_name ?? 'Technician'}
              jobs={group.jobs}
              onOpen={setOpenJobId}
            />
          ))}
          {assigned.length === 0 && (
            <Card className="flex min-w-[260px] flex-1 items-center justify-center">
              <CardContent className="py-10 text-center text-sm text-muted-foreground">
                Nobody assigned today.
                <br />
                <Link className="underline" href="/complaint-management/technicians">
                  Manage technicians
                </Link>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {openJobId && selected.data && (
        <ServiceJobPanel
          // Keyed, so opening a second job remounts rather than inheriting the first
          // job's half-typed date and "agreed by" text.
          key={selected.data.id}
          job={selected.data}
          technicians={technicians.data ?? []}
          open={Boolean(openJobId)}
          onOpenChange={(next) => {
            if (!next) setOpenJobId(null);
          }}
        />
      )}
    </div>
  );
}
