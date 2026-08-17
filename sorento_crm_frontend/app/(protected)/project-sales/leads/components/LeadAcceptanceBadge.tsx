'use client';

import * as React from 'react';
import { Badge } from '@/components/ui/badge';
import type { LeadWithAcceptance } from '../../_shared/types/leadAcceptance.types';
import {
  acceptanceBadgeVariant,
  acceptanceLabel,
  describeWait,
  hoursSince,
} from './acceptance';

/**
 * Where a lead stands in the handshake, and how long it has been standing there.
 *
 * The wait is part of the state, not a separate column: an unaccepted lead is nobody's
 * job, and how long that has been true is the whole point.
 */
export function LeadAcceptanceBadge({
  lead,
  hoursSinceAssigned,
  className,
}: {
  lead: Pick<
    LeadWithAcceptance,
    'acceptance_state' | 'owner_name' | 'assigned_at' | 'accepted_at'
  >;
  /** Supplied by the worklist, which gets it from the server. */
  hoursSinceAssigned?: number | null;
  className?: string;
}) {
  const state = lead.acceptance_state ?? null;
  const waiting =
    state === 'assigned'
      ? describeWait(hoursSinceAssigned ?? hoursSince(lead.assigned_at))
      : null;

  return (
    <span className={className}>
      <Badge variant={acceptanceBadgeVariant(state)} appearance="light">
        {acceptanceLabel(lead)}
      </Badge>
      {waiting && (
        <span className="ms-1.5 text-xs text-muted-foreground">Waiting {waiting}</span>
      )}
    </span>
  );
}
