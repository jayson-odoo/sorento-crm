'use client';

import * as React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { EventTimeline, type TimelineEvent } from '@/components/common/EventTimeline';
import { parseDateTimeAsUTC } from '@/lib/helpers';
import type { LeadWithAcceptance } from '../../../_shared/types/leadAcceptance.types';
import { informantSummary } from '../../components/acceptance';

/**
 * What has happened to this lead, in order.
 *
 * Built from the stamps the lead already carries rather than from an activity feed:
 * leads register no activities adapter on the server, so a feed tab would 400 while
 * the record itself already knows when it was recorded, handed over, answered and
 * settled. Deriving costs no request and cannot disagree with the cards.
 *
 * An entry with no stamp is still shown, dated honestly as unknown. Disqualifying
 * records a reason but no time, and silently dropping the entry would read as though
 * the lead were still open.
 */
type TimelineEntry = {
  key: string;
  at: string | null;
  label: string;
  detail?: string | null;
};

export function buildLeadTimeline(lead: LeadWithAcceptance): TimelineEntry[] {
  const entries: TimelineEntry[] = [];

  if (lead.created_at) {
    entries.push({
      key: 'recorded',
      at: lead.created_at,
      label: 'Lead recorded',
      detail: informantSummary(lead),
    });
  }
  if (lead.assigned_at) {
    entries.push({
      key: 'assigned',
      at: lead.assigned_at,
      label: lead.owner_name ? `Assigned to ${lead.owner_name}` : 'Assigned',
    });
  }
  if (lead.accepted_at) {
    entries.push({
      key: 'accepted',
      at: lead.accepted_at,
      label: lead.owner_name ? `Accepted by ${lead.owner_name}` : 'Accepted',
    });
  }
  if (lead.declined_at || lead.declined_reason) {
    entries.push({
      key: 'declined',
      at: lead.declined_at ?? null,
      label: 'Declined',
      detail: lead.declined_reason,
    });
  }
  if (lead.qualified_at) {
    entries.push({
      key: 'qualified',
      at: lead.qualified_at,
      label: 'Qualified',
      detail:
        lead.project_count > 0
          ? `${lead.project_count} project${lead.project_count === 1 ? '' : 's'} registered`
          : null,
    });
  }
  if (lead.outcome === 'disqualified') {
    entries.push({
      key: 'disqualified',
      at: null,
      label: 'Disqualified',
      detail: lead.disqualified_reason
        ? lead.disqualified_reason.replace(/_/g, ' ')
        : null,
    });
  }

  // Newest first, and anything undated last: an entry with no stamp cannot claim a
  // position among the ones that have one.
  return entries.sort((a, b) => {
    if (!a.at && !b.at) return 0;
    if (!a.at) return 1;
    if (!b.at) return -1;
    return parseDateTimeAsUTC(b.at).getTime() - parseDateTimeAsUTC(a.at).getTime();
  });
}

export function LeadTimelinePanel({ lead }: { lead: LeadWithAcceptance }) {
  const entries = React.useMemo(() => buildLeadTimeline(lead), [lead]);

  // The same rail the project's Activity tab draws, so a lead and the project it becomes
  // read as one continuous story rather than two different products.
  const events = React.useMemo<TimelineEvent[]>(
    () =>
      entries.map((entry, index) => ({
        id: entry.key,
        title: entry.label,
        at: entry.at,
        detail: entry.detail,
        tone:
          entry.key === 'declined' || entry.key === 'disqualified'
            ? 'alert'
            : index === 0
              ? 'current'
              : 'default',
      })),
    [entries],
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Activity</CardTitle>
      </CardHeader>
      <CardContent>
        <EventTimeline
          events={events}
          emptyTitle="Nothing has happened to this lead yet"
        />
      </CardContent>
    </Card>
  );
}
