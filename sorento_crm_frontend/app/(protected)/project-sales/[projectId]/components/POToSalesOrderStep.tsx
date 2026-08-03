'use client';

import * as React from 'react';
import Link from 'next/link';
import { ArrowRight, CalendarClock, CheckCircle2, FileCheck2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { ProjectPurchaseOrder } from '../../_shared/types/project.types';
import { InfoHint } from './InfoHint';

/**
 * What to do next with a purchase order that has arrived.
 *
 * The client uploaded their PO, landed here, and asked: "so how do I convert to SO?".
 * The answer was a button on a different tab that nothing pointed at, which is a
 * failure of the journey rather than of the wording. The whole feature exists to turn
 * a PO into sales orders, so the step after this one has to be visible from the PO.
 *
 * It states its prerequisites rather than being a dead control. Building needs a
 * confirmed PO AND a confirmed delivery schedule, and a disabled button that does not
 * say why is the thing people file a bug about.
 *
 * The title is the next action and stays on the card. The reason behind it (`body`) was
 * a paragraph on every expanded PO, which is a lesson repeated once per row; it now sits
 * behind the info icon, where somebody who wants the why can still get it.
 */

export type SalesOrderReadiness = {
  /** The PO has been through the confirm screen and its lines are agreed. */
  poConfirmed: boolean;
  /** A delivery schedule for this PO has been reconciled and confirmed. */
  scheduleConfirmed: boolean;
};

export function poToSalesOrderStep(readiness: SalesOrderReadiness) {
  if (!readiness.poConfirmed) {
    return {
      state: 'confirm-po' as const,
      title: 'Confirm this PO before it becomes a sales order',
      // Naming the artefact rather than the screen: they know what a PO is, and they
      // do not yet know what we called the page.
      body: 'Check what was read off the document, deal with any handwriting on it, and confirm. Nothing is ordered until you do.',
      actionLabel: 'Open the PO for checking',
    };
  }
  if (!readiness.scheduleConfirmed) {
    return {
      state: 'need-schedule' as const,
      title: 'Add the delivery schedule to build the sales orders',
      // The reason is the useful half. Quantities alone cannot be scheduled, and a
      // person who knows that will go and find the schedule rather than retry.
      body: 'The PO says what they ordered. The delivery schedule says when each phase needs it, and a sales order needs both.',
      actionLabel: 'Go to delivery schedules',
    };
  }
  return {
    state: 'ready' as const,
    title: 'Ready to build the sales orders',
    body: 'The PO and its delivery schedule are both confirmed. Building proposes the split, prices every line and lists anything that needs a decision.',
    actionLabel: 'Build the sales orders',
  };
}

export function POToSalesOrderStep({
  projectId,
  purchaseOrder,
  readiness,
}: {
  projectId: string;
  purchaseOrder: ProjectPurchaseOrder;
  readiness: SalesOrderReadiness;
}) {
  const step = poToSalesOrderStep(readiness);

  // Each destination carries what the person already chose, so the next screen does
  // not ask them to pick the PO they are standing on.
  const href =
    step.state === 'confirm-po'
      ? `/project-sales/${projectId}?tab=pos&po=${purchaseOrder.id}`
      : step.state === 'need-schedule'
        ? `/project-sales/${projectId}?tab=schedules&po=${purchaseOrder.id}`
        : `/project-sales/${projectId}?tab=sales-orders&build=${purchaseOrder.id}`;

  const Icon =
    step.state === 'ready'
      ? CheckCircle2
      : step.state === 'need-schedule'
        ? CalendarClock
        : FileCheck2;

  return (
    <div
      data-testid="po-next-step"
      data-state={step.state}
      className="mt-4 flex flex-col gap-3 rounded-lg border bg-muted/40 p-4 sm:flex-row sm:items-center sm:justify-between"
    >
      <div className="flex min-w-0 items-center gap-3">
        <Icon className="size-5 shrink-0 text-muted-foreground" aria-hidden />
        <div className="flex min-w-0 items-center gap-1">
          <p className="min-w-0 break-words font-medium">{step.title}</p>
          <InfoHint label="Why this is the next step">{step.body}</InfoHint>
        </div>
      </div>
      <Button asChild size="sm" variant={step.state === 'ready' ? 'primary' : 'outline'}>
        <Link href={href}>
          {step.actionLabel}
          <ArrowRight className="size-4" aria-hidden />
        </Link>
      </Button>
    </div>
  );
}
