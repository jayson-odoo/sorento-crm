'use client';

import { Wrench } from 'lucide-react';
import { DropdownMenuItem } from '@/components/ui/dropdown-menu';
import { useHasPermission } from '@/hooks/usePermissions';
import { useComplaintServiceJobs, useRaiseServiceJob } from '../../service-jobs/hooks/useServiceJobs';

const DEAD = ['verified', 'cancelled'];

/**
 * The complaint gear's only way to raise a service job: offered with the dispatch permission and
 * no live job (Proposed to Completed). It re-evaluates whenever the complaint's jobs refetch.
 */
export default function RaiseServiceJobMenuItem({ complaintId }: { complaintId: string }) {
  const canDispatch = useHasPermission('complaint_management.service_jobs.dispatch');
  const { data: jobs, isLoading } = useComplaintServiceJobs(complaintId);
  const raise = useRaiseServiceJob();
  if (!canDispatch || isLoading || !jobs) return null;
  if (jobs.some((j) => !DEAD.includes(j.status))) return null;
  return (
    <DropdownMenuItem disabled={raise.isPending} onSelect={() => raise.mutate(complaintId)}>
      <Wrench className="size-4" />
      Raise service job
    </DropdownMenuItem>
  );
}
