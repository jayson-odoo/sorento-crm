'use client';

import { PageHeader } from '@/components/common/PageHeader';
import BackToList from '@/components/common/BackToList';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDateInMalaysia } from '@/lib/helpers';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
import { ProjectForm } from '../../_shared/components/ProjectForm';
import { useProjectRegistration } from '../hooks/useProjectRegistrations';
import { ProjectRegistrationDuplicates } from './ProjectRegistrationDuplicates';
import { REGISTRATION_STATUS_LABELS } from './ProjectRegistrationsList';

const CRUMBS = [
  { title: 'Project Sales' },
  { title: 'Registrations', path: '/project-sales/registrations' },
  { title: 'Register project' },
];

function Meta({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <span className="min-w-0">
      <span className="text-muted-foreground">{label} </span>
      <span className="font-medium" title={value || undefined}>
        {value || '-'}
      </span>
    </span>
  );
}

export default function ProjectRegistrationReview({ id }: { id: string }) {
  const { data, isLoading, error } = useProjectRegistration(id);

  const actions = (
    <BackToList listPath="/project-sales/registrations" label="Back to registrations" />
  );

  if (!data) {
    return (
      <>
        <PageHeader title="Register project" crumbs={CRUMBS} actions={actions} />
        {isLoading ? (
          <Skeleton className="h-64 w-full" />
        ) : (
          <p className="text-sm text-destructive">
            {error instanceof Error ? error.message : 'Registration not found'}
          </p>
        )}
      </>
    );
  }

  return (
    <>
      <PageHeader
        title={
          <span className="flex min-w-0 items-center gap-3">
            <span>Register project</span>
            <span className={`${STATUS_PILL_BASE} ${statusPillClass(data.status)}`}>
              {REGISTRATION_STATUS_LABELS[data.status] ?? data.status}
            </span>
          </span>
        }
        crumbTitle="Register project"
        crumbs={CRUMBS}
        actions={actions}
      />

      <div className="space-y-2 text-sm">
        <div className="flex flex-wrap gap-x-6 gap-y-1">
          <Meta
            label="Date"
            value={data.submitted_at ? formatDateInMalaysia(data.submitted_at) : null}
          />
          <Meta label="Sales agent" value={data.sales_agent_name} />
          <Meta label="Distributor" value={data.distributor_name} />
          <Meta label="Customer" value={data.customer_name} />
          <Meta label="Your ref" value={data.your_ref} />
          {data.project_code && <Meta label="Project" value={data.project_code} />}
        </div>
        {data.status === 'rejected' && data.reject_reason && (
          <p className="text-destructive">Rejected: {data.reject_reason}</p>
        )}
        {data.possible_duplicates.length > 0 && (
          <p className="flex min-w-0 gap-1">
            <span className="shrink-0 text-muted-foreground">Possible duplicate:</span>
            <ProjectRegistrationDuplicates items={data.possible_duplicates} />
          </p>
        )}
      </div>

      <ProjectForm mode="review" registration={data} />
    </>
  );
}
