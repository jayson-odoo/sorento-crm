'use client';

/**
 * One service job, on its own page.
 *
 * Until now a job could only be opened from the dispatch board, which is one day - so a
 * job proposed with no date, or confirmed for a day already past, had no address anywhere
 * in the product. It existed, it was linked to a complaint, and there was no way to look
 * at it.
 *
 * The actions stay in `ServiceJobPanel` rather than being reimplemented here. That panel
 * is where the confirm-needs-a-date-AND-an-agreement rule lives (AC-F5) and where the
 * graph decides which moves are offered; a second copy would drift from it, and the copy
 * that drifts is the one that offers a move the server refuses.
 */

import { use, useState } from 'react';
import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
import { formatDateTimeInMalaysia } from '@/lib/helpers';

import { ServiceJobPanel } from '../components/ServiceJobPanel';
import {
  SERVICE_JOB_STATUS_LABELS,
  formatDuration,
  getServiceJob,
  listTechnicians,
  type ServiceJobStatusKey,
} from '../services/serviceJobService';

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <p className="text-sm text-muted-foreground">{label}</p>
      <div className="font-medium break-words">{value ?? '-'}</div>
    </div>
  );
}

/** Where the job came from. Polymorphic by design (ADR-0009), so the link is built from
 *  the pair rather than assuming a complaint - even though a complaint is all there is
 *  today. */
function sourceHref(type: string, id: string): string | null {
  if (type === 'complaint') return `/complaint-management/complaints/${id}`;
  return null;
}

export default function ServiceJobDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const [panelOpen, setPanelOpen] = useState(false);

  const job = useQuery({ queryKey: ['service-job', id], queryFn: () => getServiceJob(id) });
  const technicians = useQuery({
    queryKey: ['technicians', 'active'],
    queryFn: () => listTechnicians({ isActive: true }),
  });

  if (job.isLoading) {
    return (
      <div className="p-4 sm:p-6">
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (job.isError || !job.data) {
    return (
      <div className="p-4 sm:p-6">
        <p className="text-sm text-muted-foreground">
          {(job.error as Error)?.message ?? 'Service job not found.'}
        </p>
      </div>
    );
  }

  const data = job.data;
  const backHref = sourceHref(data.source_entity_type, data.source_entity_id);

  return (
    <div className="flex flex-col gap-4 p-4 sm:p-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center gap-2">
          <Button variant="ghost" size="icon" asChild>
            <Link href="/complaint-management/service-jobs">
              <ArrowLeft className="size-4" />
            </Link>
          </Button>
          <h1 className="min-w-0 text-xl font-semibold break-words">
            {data.job_number ?? 'Service job'}
          </h1>
          <span className={`${STATUS_PILL_BASE} ${statusPillClass(data.status_key)}`}>
            {data.status_key
              ? SERVICE_JOB_STATUS_LABELS[data.status_key as ServiceJobStatusKey]
              : 'Unknown'}
          </span>
        </div>
        <div className="flex flex-wrap gap-2">
          {backHref && (
            <Button variant="outline" asChild>
              <Link href={backHref}>Open complaint</Link>
            </Button>
          )}
          <Button onClick={() => setPanelOpen(true)}>Update job</Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Visit</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <Field
            label="Scheduled"
            value={
              data.scheduled_from ? (
                formatDateTimeInMalaysia(data.scheduled_from)
              ) : (
                <span className="text-muted-foreground">Not scheduled</span>
              )
            }
          />
          <Field label="Agreed by" value={data.customer_agreed_by} />
          <Field
            label="Arrived"
            value={data.arrived_at ? formatDateTimeInMalaysia(data.arrived_at) : '-'}
          />
          <Field
            label="Attended in"
            value={data.attend_seconds !== null ? formatDuration(data.attend_seconds) : '-'}
          />
          <Field
            label="Completed"
            value={data.completed_at ? formatDateTimeInMalaysia(data.completed_at) : '-'}
          />
          <Field
            label="Verified"
            value={data.verified_at ? formatDateTimeInMalaysia(data.verified_at) : '-'}
          />
          {data.waiting_on_party && (
            <Field
              label="Waiting on"
              value={`${data.waiting_on_party}${
                data.waiting_on_reason ? ` (${data.waiting_on_reason})` : ''
              }`}
            />
          )}
        </CardContent>
      </Card>

      {/* Always rendered, per the CRUD standard. A job with no site is a van with nowhere
          to go, and hiding the section makes that invisible. */}
      <Card>
        <CardHeader>
          <CardTitle>Site</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <Field
            label="Address"
            value={
              data.site_address ?? (
                <span className="text-sm text-muted-foreground">
                  No site recorded on this job.
                </span>
              )
            }
          />
          <Field
            label="Contact on site"
            value={
              [data.site_contact_name, data.site_contact_phone].filter(Boolean).join(' · ') ||
              '-'
            }
          />
        </CardContent>
      </Card>

      {panelOpen && technicians.data && (
        <ServiceJobPanel
          job={data}
          technicians={technicians.data}
          open={panelOpen}
          onOpenChange={setPanelOpen}
        />
      )}
    </div>
  );
}
