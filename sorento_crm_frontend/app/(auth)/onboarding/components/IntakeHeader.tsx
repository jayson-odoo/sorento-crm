'use client';

/**
 * What the requester is told before she is asked for anything.
 *
 * Everything here is something the system already knew when the link was minted
 * - her company, who asked her, when the link stops working - so none of it is
 * a question. Per the journey, step 1 asks for zero decisions.
 */

import { CalendarClock, Building2, UserRound } from 'lucide-react';
import type {
  OnboardingIntakeContext,
  OnboardingRequestStatus,
} from '@/components/common/onboarding/types';
import { ONBOARDING_STATUS_LABELS } from '@/components/common/onboarding/types';
import { statusPillClass, STATUS_PILL_BASE } from '@/lib/status-pill';

function formatDay(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });
}

export function IntakeHeader({ context }: { context: OnboardingIntakeContext }) {
  const status: OnboardingRequestStatus = context.status;
  return (
    <header className="flex flex-col gap-3">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold break-words">{context.title}</h1>
          <p className="text-sm text-muted-foreground break-words">
            Sorento asks you to submit your team for onboarding.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className={`${STATUS_PILL_BASE} ${statusPillClass(status)}`}>
            {ONBOARDING_STATUS_LABELS[status]}
          </span>
        </div>
      </div>

      <dl className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-3">
        <div className="flex items-center gap-2 min-w-0">
          <Building2 className="size-4 text-muted-foreground shrink-0" />
          <dt className="sr-only">Company</dt>
          <dd className="truncate" title={context.company_name}>
            {context.company_name}
          </dd>
        </div>
        <div className="flex items-center gap-2 min-w-0">
          <UserRound className="size-4 text-muted-foreground shrink-0" />
          <dt className="sr-only">Requested from</dt>
          <dd className="truncate" title={context.requester_name}>
            {context.requester_name}
          </dd>
        </div>
        <div className="flex items-center gap-2 min-w-0">
          <CalendarClock className="size-4 text-muted-foreground shrink-0" />
          <dt className="sr-only">Link expires</dt>
          <dd className="truncate">Link valid until {formatDay(context.expires_at)}</dd>
        </div>
      </dl>
    </header>
  );
}
