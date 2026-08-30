'use client';

import * as React from 'react';
import { Flame } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import { useUpdateProject } from '../../_shared/hooks/useProjects';
import type { Project } from '../../_shared/types/project.types';
import { InfoHint } from './InfoHint';

/**
 * The PDF's "Final Negotiation", as a flag rather than a funnel stage (AC-G7).
 *
 * A stage would force a re-quote during negotiation to move the card backwards, which
 * corrupts every stage-duration number. As a flag it can be set at any stage, and the
 * date it was raised is what "days in final negotiation" counts from -- so re-saving
 * the notes must not restart that clock, which the server enforces.
 */
export function CriticalPanel({ project }: { project: Project }) {
  const update = useUpdateProject(project.id);
  const [support, setSupport] = React.useState(project.management_support ?? '');
  const [notes, setNotes] = React.useState(project.management_notes ?? '');

  React.useEffect(() => {
    setSupport(project.management_support ?? '');
    setNotes(project.management_notes ?? '');
  }, [project.management_support, project.management_notes]);

  const dirty =
    support !== (project.management_support ?? '') || notes !== (project.management_notes ?? '');

  return (
    <Card>
      <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center gap-1">
          <CardTitle className="flex items-center gap-2 text-sm">
            <Flame
              className={project.is_critical ? 'size-4 text-destructive' : 'size-4 text-muted-foreground'}
              aria-hidden
            />
            Critical / final negotiation
          </CardTitle>
          <InfoHint label="About the critical flag">
            A flag, not a stage, so raising it never drags the card backwards. Turning it
            off clears the clock, and a second escalation is timed afresh.
          </InfoHint>
        </div>
        <div className="flex items-center gap-2">
          <Switch
            id="project-critical"
            checked={project.is_critical}
            disabled={!project.can_edit || update.isPending}
            onCheckedChange={(next) => update.mutate({ is_critical: next })}
          />
          <Label htmlFor="project-critical" className="text-xs">
            {project.is_critical ? 'Raised' : 'Not raised'}
          </Label>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Kept because it reports THIS project: when it was raised, and how long it has
            been in negotiation. The rule behind the flag moved to the icon above. */}
        {project.is_critical && (
          <p className="text-xs text-muted-foreground">
            Raised {formatDate(project.critical_at) ?? 'recently'}
            {project.critical_at
              ? ` · ${daysSince(project.critical_at)} days in negotiation`
              : ''}
          </p>
        )}

        <div className="space-y-1.5">
          <Label htmlFor="management-support">Management support committed</Label>
          <Textarea
            id="management-support"
            value={support}
            onChange={(event) => setSupport(event.target.value)}
            disabled={!project.can_edit}
            rows={2}
            placeholder="e.g. Price approval to 18% below list, free samples for the mock-up unit"
          />
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="management-notes">Notes</Label>
          <Textarea
            id="management-notes"
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
            disabled={!project.can_edit}
            rows={3}
            placeholder="What was agreed, with whom, and what is still open"
          />
        </div>

        {project.can_edit && (
          <div className="flex justify-end gap-2">
            {dirty && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => {
                  setSupport(project.management_support ?? '');
                  setNotes(project.management_notes ?? '');
                }}
              >
                Discard
              </Button>
            )}
            <Button
              type="button"
              size="sm"
              disabled={!dirty || update.isPending}
              onClick={() =>
                update.mutate({
                  management_support: support.trim() || null,
                  management_notes: notes.trim() || null,
                })
              }
            >
              Save management notes
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function formatDate(iso?: string | null): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleDateString('en-MY', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  });
}

function daysSince(iso: string): number {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return 0;
  return Math.max(0, Math.floor((Date.now() - then) / 86_400_000));
}
