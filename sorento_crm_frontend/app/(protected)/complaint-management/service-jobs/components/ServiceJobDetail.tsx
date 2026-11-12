'use client';

import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DropdownMenuItem } from '@/components/ui/dropdown-menu';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import DetailActions from '@/components/common/DetailActions';
import { DetailActionsMenu } from '@/components/common/DetailActionsMenu';
import AuditTrail from '@/components/audit/AuditTrail';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { useUrlTab } from '@/hooks/useUrlTab';
import { useServiceJob } from '../hooks/useServiceJobs';
import { useServiceJobMoves } from '../hooks/useServiceJobMoves';
import { nextStepFor, secondaryMoves } from '../lib/nextStep';
import { serviceJobsPagerQuery } from '../lib/listQuery';
import ServiceJobStatusPill from './ServiceJobStatusPill';

const TABS = ['details', 'history'] as const;

function dash(value: string | null | undefined): string {
  return value && value.trim() ? value : '-';
}

function when(value: string | null | undefined): string {
  return value ? formatDateTimeInMalaysia(value) || '-' : '-';
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid grid-cols-[9rem_1fr] gap-2 py-1.5 text-sm">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="min-w-0 break-words">{value}</dd>
    </div>
  );
}

export default function ServiceJobDetail({ jobId }: { jobId: string }) {
  const { data: job, isLoading } = useServiceJob(jobId);
  const moves = useServiceJobMoves();
  const [tab, setTab] = useUrlTab({ tabs: TABS, defaultTab: 'details' });

  if (isLoading || !job) {
    return isLoading ? (
      <div className="space-y-6">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-64 w-full" />
      </div>
    ) : (
      <p className="py-12 text-center text-muted-foreground">Service job not found</p>
    );
  }

  const step = nextStepFor(job);
  const secondary = secondaryMoves(job.status, !!job.technician_id);
  const canChangeTechnician =
    !!job.technician_id && (job.status === 'proposed' || job.status === 'confirmed');

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-2xl font-bold break-words">{job.job_number}</h2>
            <ServiceJobStatusPill status={job.status} label={job.status_label} />
          </div>
          <p className="text-sm text-muted-foreground">
            {[job.complaint_number, job.customer_name].filter(Boolean).join(' · ') || '-'}
          </p>
        </div>
        <DetailActions
          pager={{
            ...serviceJobsPagerQuery,
            detailPath: '/complaint-management/service-jobs',
            currentId: jobId,
            ariaLabel: 'service job',
          }}
          gear={
            <DetailActionsMenu ariaLabel="Service job actions">
              {canChangeTechnician && (
                <DropdownMenuItem
                  onSelect={(e) => {
                    e.preventDefault();
                    moves.changeTechnician(job);
                  }}
                >
                  Change technician
                </DropdownMenuItem>
              )}
              {secondary.map((m) => (
                <DropdownMenuItem
                  key={`${m.to}-${m.label}`}
                  onSelect={(e) => {
                    e.preventDefault();
                    moves.runMove(job, m);
                  }}
                >
                  {m.label}
                </DropdownMenuItem>
              ))}
              <DropdownMenuItem asChild>
                <Link href={`/complaint-management/complaints/${job.complaint_id}`}>Open complaint</Link>
              </DropdownMenuItem>
            </DetailActionsMenu>
          }
          primary={
            step ? (
              <Button onClick={() => moves.runStep(job, step)} disabled={moves.isPending}>
                {step.label}
              </Button>
            ) : undefined
          }
          dialogs={moves.dialogs}
        />
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList variant="line" className="mb-5">
          <TabsTrigger value="details">Details</TabsTrigger>
          <TabsTrigger value="history">History</TabsTrigger>
        </TabsList>
        <TabsContent value="details" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Visit</CardTitle>
            </CardHeader>
            <CardContent>
              <dl>
                <Field label="Scheduled" value={when(job.scheduled_from)} />
                <Field label="Technician" value={dash(job.technician_name)} />
                <Field label="Agreed by" value={dash(job.customer_agreed_by)} />
                <Field label="Arrived" value={when(job.arrived_at)} />
                <Field label="Completed" value={when(job.completed_at)} />
                <Field label="Verified" value={when(job.verified_at)} />
                {job.rejection_reason && <Field label="Last rejection" value={job.rejection_reason} />}
                {job.cancel_reason && <Field label="Cancelled because" value={job.cancel_reason} />}
              </dl>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Site</CardTitle>
            </CardHeader>
            <CardContent>
              <dl>
                <Field label="Address line 1" value={dash(job.site_address_line1)} />
                <Field label="Address line 2" value={dash(job.site_address_line2)} />
                <Field label="Postcode" value={dash(job.site_postcode)} />
                <Field label="City" value={dash(job.city)} />
                <Field label="State" value={dash(job.site_state)} />
                <Field label="Country" value={dash(job.site_country)} />
                <Field label="Contact on site" value={dash(job.site_contact_name)} />
                <Field label="Contact phone" value={dash(job.site_contact_phone)} />
              </dl>
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="history">
          <AuditTrail entityType="service_jobs" entityId={jobId} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
