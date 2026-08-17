'use client';

import * as React from 'react';
import { useQueries } from '@tanstack/react-query';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import {
  useQuotations,
  useSampleMutations,
  versionsKey,
} from '../../_shared/hooks/useProjects';
import { listQuotationVersions } from '../../_shared/services/projectService';
import type { Project, ProjectSample } from '../../_shared/types/project.types';

/**
 * Record a sample against a quotation version.
 *
 * On CREATE only the current version of each scope is offered: submitting against a
 * superseded one is refused server-side (AC-F2), and offering a choice the server will
 * reject is worse than not offering it. On EDIT the version is fixed and shown as text,
 * because re-binding an existing sample to a different price is a new submission wearing
 * an edit -- and the feedback being captured is usually the reason the version moved on.
 */
export function SampleDialog({
  project,
  sample,
  onDone,
}: {
  project: Project;
  sample: ProjectSample | null;
  onDone: () => void;
}) {
  const { create, update } = useSampleMutations(project.id);
  const quotations = useQuotations(project.id);

  const scopes = React.useMemo(() => quotations.data ?? [], [quotations.data]);

  // The current version id already comes back on each quotation, so this only needs the
  // version LIST when the label has to name a version that is not the current one.
  const versionQueries = useQueries({
    queries: scopes.map((scope) => ({
      queryKey: versionsKey(scope.id),
      queryFn: () => listQuotationVersions(scope.id),
      enabled: !sample,
    })),
  });

  const [versionId, setVersionId] = React.useState(sample?.quotation_version_id ?? '');
  const [submittedOn, setSubmittedOn] = React.useState(sample?.submitted_on ?? '');
  const [feedback, setFeedback] = React.useState(sample?.developer_feedback ?? '');
  const [notes, setNotes] = React.useState(sample?.salesperson_notes ?? '');

  const isEdit = Boolean(sample);
  const pending = create.isPending || update.isPending;

  const versionOptions = React.useMemo(() => {
    return scopes.flatMap((scope, index) => {
      const versions = versionQueries[index]?.data ?? [];
      const current = versions.find((version) => version.is_current);
      if (!current) return [];
      return [
        {
          value: current.id,
          label: `${scope.scope_label} v${current.version_no}`,
          description: scope.series_name ?? undefined,
        },
      ];
    });
  }, [scopes, versionQueries]);

  const blocked = !isEdit && !versionId;

  return (
    <Dialog open onOpenChange={(next) => !next && onDone()}>
      <DialogContent className="max-h-[92vh] w-full max-w-lg overflow-hidden">
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Edit sample submission' : 'Record a sample'}</DialogTitle>
          <DialogDescription>
            A sample is tied to the price it was sent against, so an approval can always
            be traced back to a number.
          </DialogDescription>
        </DialogHeader>

        <form
          onSubmit={async (event) => {
            event.preventDefault();
            const body = {
              submitted_on: submittedOn || null,
              developer_feedback: feedback.trim() || null,
              salesperson_notes: notes.trim() || null,
            };
            if (sample) {
              await update.mutateAsync({ id: sample.id, body });
            } else {
              await create.mutateAsync({ ...body, quotation_version_id: versionId });
            }
            onDone();
          }}
        >
          <DialogBody className="max-h-[65vh] space-y-4 overflow-y-auto">
            {isEdit ? (
              <div className="space-y-1.5">
                <Label>Sent against</Label>
                <p className="rounded-md border border-border bg-muted/40 px-3 py-2 text-sm">
                  {sample?.scope_label ?? 'Unnamed scope'}
                  {sample?.version_no ? ` v${sample.version_no}` : ''}
                  {sample && !sample.is_version_current && ' (since superseded)'}
                </p>
                <p className="text-xs text-muted-foreground">
                  The binding does not change on an edit. Record a new sample to send
                  against a newer version.
                </p>
              </div>
            ) : (
              <div className="space-y-1.5">
                <Label htmlFor="sample-version">
                  Sent against <span className="text-destructive">*</span>
                </Label>
                <SearchableSelect
                  id="sample-version"
                  value={versionId}
                  onChange={setVersionId}
                  options={versionOptions}
                  placeholder="Select a scope and version"
                  emptyMessage="Nothing is quoted on this project yet"
                />
                <p className="text-xs text-muted-foreground">
                  Only the current version of each scope is offered. A sample against a
                  superseded price is what the quotation revision was meant to prevent.
                </p>
              </div>
            )}

            <div className="space-y-1.5">
              <Label htmlFor="sample-date">Date sent</Label>
              <Input
                id="sample-date"
                type="date"
                value={submittedOn}
                onChange={(event) => setSubmittedOn(event.target.value)}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="sample-feedback">Developer feedback</Label>
              <Textarea
                id="sample-feedback"
                value={feedback}
                onChange={(event) => setFeedback(event.target.value)}
                rows={3}
                placeholder="What they said, what they want changed"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="sample-notes">Your notes</Label>
              <Textarea
                id="sample-notes"
                value={notes}
                onChange={(event) => setNotes(event.target.value)}
                rows={2}
                placeholder="Who you left it with, what to chase next"
              />
            </div>
          </DialogBody>

          <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
            <Button type="button" variant="outline" onClick={onDone}>
              Cancel
            </Button>
            <Button type="submit" disabled={blocked || pending}>
              {isEdit ? 'Save changes' : 'Record sample'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
