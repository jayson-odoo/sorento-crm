'use client';

/**
 * One job, and every action a dispatcher can take on it.
 *
 * **Confirming asks for two things and refuses on one** (AC-F5). The date and who agreed it
 * are separate inputs because they are separate facts: a date nobody agreed to is exactly
 * the "Service Date: TBA" the slice exists to make impossible. The backend refuses either
 * way, and its sentence is surfaced verbatim rather than replaced with "Something went
 * wrong" - the message names which half is missing, which is the only useful thing to say.
 *
 * **Rejecting is a confirmation dialog, not a button.** It is not destructive in the delete
 * sense, but it un-agrees a date with a customer and marks the case as waiting on them, and
 * a one-click version of that gets pressed by accident on a laptop trackpad.
 *
 * Actions are shown only where the graph allows them, so the panel cannot offer a move the
 * server will refuse. The graph is the authority either way: this is presentation, and a
 * disagreement resolves as a 422 rather than a wrong write.
 */

import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
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
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';

import {
  SERVICE_JOB_STATUS_LABELS,
  arriveAtServiceJob,
  assignServiceJob,
  completeServiceJob,
  confirmServiceJob,
  formatDuration,
  rejectServiceJobVisit,
  startServiceJobTravel,
  verifyServiceJob,
  type ServiceJob,
  type ServiceJobStatusKey,
  type Technician,
} from '../services/serviceJobService';

/** Which actions the seeded graph permits out of each state. Mirrors the transition seeds. */
const ALLOWED: Record<ServiceJobStatusKey, string[]> = {
  proposed: ['confirm', 'assign'],
  confirmed: ['assign', 'on_the_way', 'arrive', 'reject', 'confirm'],
  on_the_way: ['arrive', 'reject'],
  arrived: ['complete'],
  completed: ['verify'],
  verified: [],
  cancelled: [],
};

export interface ServiceJobPanelProps {
  job: ServiceJob;
  technicians: Technician[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-sm break-words">{value ?? <span className="text-muted-foreground">-</span>}</div>
    </div>
  );
}

export function ServiceJobPanel({ job, technicians, open, onOpenChange }: ServiceJobPanelProps) {
  const queryClient = useQueryClient();
  const [scheduledFrom, setScheduledFrom] = useState(job.scheduled_from?.slice(0, 16) ?? '');
  const [agreedBy, setAgreedBy] = useState(job.customer_agreed_by ?? '');
  const [technicianId, setTechnicianId] = useState('');
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState('');

  const allowed = ALLOWED[job.status_key ?? 'proposed'] ?? [];

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['service-job-board'] });
    queryClient.invalidateQueries({ queryKey: ['service-job-stalls'] });
    // The OPEN panel too. Without this the board behind it updates while the dialog in
    // front of it still shows the old status and still offers the action just taken -
    // which reads as the action having failed, and invites pressing it again.
    queryClient.invalidateQueries({ queryKey: ['service-job', job.id] });
  };

  const run = <T,>(fn: () => Promise<T>, success: string) =>
    fn()
      .then(() => {
        toast.success(success);
        invalidate();
      })
      .catch((error: Error) => {
        // The backend's own sentence. It names which half of AC-F5 is missing, and no
        // generic message can say that.
        toast.error(error.message);
      });

  const confirm = useMutation({
    mutationFn: () =>
      confirmServiceJob(job.id, {
        scheduled_from: scheduledFrom ? new Date(scheduledFrom).toISOString() : null,
        customer_agreed_by: agreedBy,
      }),
    onSuccess: () => {
      toast.success('Date confirmed.');
      invalidate();
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const assign = useMutation({
    mutationFn: () => assignServiceJob(job.id, technicianId),
    onSuccess: () => {
      toast.success('Technician assigned.');
      setTechnicianId('');
      invalidate();
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <span className="min-w-0 break-words">{job.job_number ?? 'Service job'}</span>
              <span className={`${STATUS_PILL_BASE} ${statusPillClass(job.status_key)}`}>
                {job.status_key ? SERVICE_JOB_STATUS_LABELS[job.status_key] : 'Unknown'}
              </span>
            </DialogTitle>
            <DialogDescription>
              Raised from a {job.source_entity_type.replace(/_/g, ' ')}.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Site" value={job.site_address} />
            <Field label="Site contact" value={job.site_contact_name} />
            <Field label="Contact phone" value={job.site_contact_phone} />
            <Field
              label="Attend time"
              value={job.attend_seconds === null ? 'Not arrived' : formatDuration(job.attend_seconds)}
            />
            <Field label="Agreed by" value={job.customer_agreed_by} />
            <Field
              label="Waiting on"
              value={
                job.waiting_on_party
                  ? `${job.waiting_on_party.replace(/_/g, ' ')} (${(job.waiting_on_reason ?? '').replace(/_/g, ' ')})`
                  : null
              }
            />
          </div>

          {allowed.includes('confirm') && (
            <div className="rounded-md border p-4">
              <div className="mb-1 text-sm font-medium">Confirm the visit</div>
              <p className="mb-3 text-xs text-muted-foreground">
                A date alone is not a confirmation. Record who agreed it, or the job stays proposed.
              </p>
              <div className="grid gap-3 sm:grid-cols-2">
                <div>
                  <Label htmlFor="scheduled-from">Date and time</Label>
                  <Input
                    id="scheduled-from"
                    type="datetime-local"
                    value={scheduledFrom}
                    onChange={(event) => setScheduledFrom(event.target.value)}
                  />
                </div>
                <div>
                  <Label htmlFor="agreed-by">Agreed by</Label>
                  <Input
                    id="agreed-by"
                    placeholder="e.g. Consumer on WhatsApp"
                    value={agreedBy}
                    onChange={(event) => setAgreedBy(event.target.value)}
                  />
                </div>
              </div>
              <Button
                className="mt-3"
                disabled={confirm.isPending}
                onClick={() => confirm.mutate()}
              >
                Confirm date
              </Button>
            </div>
          )}

          {allowed.includes('assign') && (
            <div className="rounded-md border p-4">
              <div className="mb-1 text-sm font-medium">Send a technician</div>
              <p className="mb-3 text-xs text-muted-foreground">
                Each dispatch is a new attempt. Re-assigning after a rejection keeps the first one
                in history.
              </p>
              <div className="flex flex-col gap-3 sm:flex-row">
                <SearchableSelect
                  className="sm:flex-1"
                  value={technicianId}
                  onChange={setTechnicianId}
                  placeholder="Select a technician"
                  emptyMessage="No technicians yet."
                  options={technicians.map((technician) => ({
                    value: technician.id,
                    label: technician.name,
                    description: technician.employment_type ?? undefined,
                  }))}
                />
                <Button
                  disabled={!technicianId || assign.isPending}
                  onClick={() => assign.mutate()}
                >
                  Assign
                </Button>
              </div>
            </div>
          )}

          <DialogFooter className="flex-wrap gap-2">
            {allowed.includes('on_the_way') && (
              <Button
                variant="outline"
                onClick={() => run(() => startServiceJobTravel(job.id), 'Marked on the way.')}
              >
                On the way
              </Button>
            )}
            {allowed.includes('arrive') && (
              <Button
                variant="outline"
                onClick={() => run(() => arriveAtServiceJob(job.id), 'Arrival recorded.')}
              >
                Arrived
              </Button>
            )}
            {allowed.includes('complete') && (
              <Button onClick={() => run(() => completeServiceJob(job.id), 'Job completed.')}>
                Complete
              </Button>
            )}
            {allowed.includes('verify') && (
              <Button onClick={() => run(() => verifyServiceJob(job.id), 'Job verified.')}>
                Verify
              </Button>
            )}
            {allowed.includes('reject') && (
              <Button variant="outline" onClick={() => setRejectOpen(true)}>
                Customer rejected
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={rejectOpen} onOpenChange={setRejectOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Record a rejected visit</AlertDialogTitle>
            <AlertDialogDescription>
              The job goes back to proposed and the case is marked as waiting on the customer.
              The attempt stays in history, so it is excluded from the technician&apos;s attend
              time.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div>
            <Label htmlFor="reject-reason">Reason (optional)</Label>
            <Input
              id="reject-reason"
              value={rejectReason}
              onChange={(event) => setRejectReason(event.target.value)}
              placeholder="e.g. Consumer asked to postpone"
            />
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                void run(
                  () => rejectServiceJobVisit(job.id, rejectReason || undefined),
                  'Rejected visit recorded.',
                );
                setRejectOpen(false);
                setRejectReason('');
              }}
            >
              Record rejection
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
