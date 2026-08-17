'use client';

import * as React from 'react';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { EventTimeline, type TimelineEvent } from '@/components/common/EventTimeline';
import { listActivities } from '@/components/common/ActivitiesNotesPanel/activitiesPanelService';
import type { ActivityEvent } from '@/components/common/ActivitiesNotesPanel/types';
import type { Project } from '../../_shared/types/project.types';
import { InfoHint } from './InfoHint';

/**
 * The project's activity feed (AC-H1).
 *
 * Reads the SAME generic `/api/v1/activities/project/{id}` endpoint the shared panel uses,
 * because the project registers an adapter rather than owning a notes table. This tab is the
 * always-visible history; posting, mentions and internal notes stay in the shared side panel
 * (the drawer this page is wrapped in) so there is one composer, not two.
 *
 * The reason it renders the feed at all instead of just pointing at the drawer: the staleness
 * ladder reads this history, and "which of these events counted as work" is a question people
 * will ask the first time a nudge surprises them. Meaningful events are marked, so the answer
 * is on screen rather than in a doc.
 */
const MEANINGFUL: Record<string, string> = {
  stage_changed: 'Stage changed',
  quotation_created: 'Quotation created',
  quotation_revised: 'Quotation revised',
  sample_submitted: 'Sample submitted',
  sponsorship_recorded: 'Sponsorship recorded',
  po_recorded: 'Purchase order recorded',
};

function describe(event: ActivityEvent): { text: string; meaningful: boolean } {
  const template = event.system_template ?? '';
  const known = MEANINGFUL[template];
  if (known) return { text: known, meaningful: true };
  if (event.kind === 'user_update') {
    return { text: event.body_text || 'Posted an update', meaningful: true };
  }
  return { text: event.body_text || template.replace(/_/g, ' ') || 'Activity', meaningful: false };
}

export function ProjectActivityPanel({ project }: { project: Project }) {
  const [events, setEvents] = React.useState<ActivityEvent[] | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let alive = true;
    listActivities('project', project.id, { limit: 50 })
      .then((page) => {
        if (alive) setEvents(page.items ?? []);
      })
      .catch((err: unknown) => {
        if (alive) setError(err instanceof Error ? err.message : 'Could not load the activity feed.');
      });
    return () => {
      alive = false;
    };
    // Keyed on updated_at as well as the id, not just the id. Found in the browser: moving
    // the stage cleared the staleness banner immediately (the project query refetched) while
    // this feed still showed the previous events, so the page disagreed with itself about
    // what had just happened. Same rule the SLA banner follows - key a dependent read on the
    // entity's changing field.
  }, [project.id, project.updated_at, project.stale_level]);

  // A history, not a list of records: one rail, newest first, grouped by day. See
  // components/common/EventTimeline for why this is the one surface that is not a grid.
  const timeline = React.useMemo<TimelineEvent[]>(
    () =>
      (events ?? []).map((event, index) => {
        const described = describe(event);
        return {
          id: event.id,
          title: described.text,
          actor: event.actor?.name ?? null,
          at: event.created_at ?? null,
          tone: index === 0 ? 'current' : described.meaningful ? 'default' : 'muted',
          tags: described.meaningful ? (
            <Badge variant="secondary" appearance="light" className="text-[11px]">
              counts as work
            </Badge>
          ) : null,
        };
      }),
    [events],
  );

  return (
    <Card>
      <CardHeader>
        <div className="flex min-w-0 items-center gap-1">
          <CardTitle className="text-sm">Activity</CardTitle>
          {/* Asked once, so it stays behind the icon rather than sitting in the tab. */}
          <InfoHint label="About the activity feed">
            Events marked <span className="font-medium">counts as work</span> reset the
            staleness clock. Ordinary edits and imports do not.
          </InfoHint>
        </div>
      </CardHeader>
      <CardContent>
        {error ? (
          <p className="text-sm text-destructive">{error}</p>
        ) : events === null ? (
          <div className="space-y-2">
            <Skeleton className="h-5 w-3/4" />
            <Skeleton className="h-5 w-2/3" />
          </div>
        ) : (
          <EventTimeline events={timeline} emptyTitle="Nothing recorded yet" />
        )}
      </CardContent>
    </Card>
  );
}
