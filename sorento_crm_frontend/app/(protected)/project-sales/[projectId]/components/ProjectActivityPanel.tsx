'use client';

import * as React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { listActivities } from '@/components/common/ActivitiesNotesPanel/activitiesPanelService';
import type { ActivityEvent } from '@/components/common/ActivitiesNotesPanel/types';
import type { Project } from '../../_shared/types/project.types';

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

  return (
    <Card>
      <CardHeader className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <CardTitle className="text-sm">Activity</CardTitle>
        <p className="text-xs text-muted-foreground">
          Events marked <span className="font-medium">counts as work</span> reset the staleness
          clock. Ordinary edits and imports deliberately do not.
        </p>
      </CardHeader>
      <CardContent>
        {error ? (
          <p className="text-sm text-destructive">{error}</p>
        ) : events === null ? (
          <div className="space-y-2">
            <Skeleton className="h-5 w-3/4" />
            <Skeleton className="h-5 w-2/3" />
          </div>
        ) : events.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Nothing recorded yet. Moving the stage, pricing a scope, submitting a sample or
            recording a purchase order all appear here, as does anything you post from the
            activity panel.
          </p>
        ) : (
          <ul className="space-y-3">
            {events.map((event) => {
              const described = describe(event);
              return (
                <li key={event.id} className="flex flex-col gap-0.5 border-b border-border/60 pb-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm">{described.text}</span>
                    {described.meaningful && (
                      <span className="rounded border border-border px-1.5 py-0.5 text-[11px] text-muted-foreground">
                        counts as work
                      </span>
                    )}
                  </div>
                  <span className="text-xs text-muted-foreground">
                    {[
                      event.actor?.name ?? null,
                      event.created_at ? new Date(event.created_at).toLocaleString() : null,
                    ]
                      .filter(Boolean)
                      .join(' · ')}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
