'use client';

import * as React from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  useCollaborators,
  useTakeoverMutations,
  useTakeoverRequests,
} from '../../_shared/hooks/useProjects';
import type { Project } from '../../_shared/types/project.types';

/**
 * Who may work this project, and the recorded history of how that was decided.
 *
 * This panel is the visible half of ADR-0004. Blocking a registration only works if
 * the blocked person has somewhere to go, and the decision has to leave a trail:
 * "Ali approved Siti onto PRJ-000123 in March, here is the reason" is what stops the
 * same argument recurring in WhatsApp.
 */
export function ProjectAccessPanel({ project }: { project: Project }) {
  const collaborators = useCollaborators(project.id);
  const requests = useTakeoverRequests(project.id);
  const { decide } = useTakeoverMutations(project.id);
  const [requesting, setRequesting] = React.useState<'join' | 'dispute' | null>(null);

  const pending = (requests.data ?? []).filter((request) => request.status === 'pending');
  const decided = (requests.data ?? []).filter((request) => request.status !== 'pending');

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Access</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <p className="text-xs text-muted-foreground">Owner</p>
            <p className="text-sm font-medium">{project.owner_name ?? 'Unassigned'}</p>
          </div>

          <div>
            <p className="text-xs text-muted-foreground">Collaborators</p>
            {collaborators.isLoading ? (
              <p className="text-sm text-muted-foreground">Loading…</p>
            ) : (collaborators.data ?? []).length === 0 ? (
              <p className="text-sm text-muted-foreground">-</p>
            ) : (
              <ul className="mt-1 space-y-1">
                {collaborators.data!.map((collaborator) => (
                  <li key={collaborator.user_id} className="text-sm">
                    {collaborator.user_name ?? 'Unknown user'}
                  </li>
                ))}
              </ul>
            )}
          </div>

          {!project.can_edit && (
            <div className="space-y-2 rounded-md border border-border bg-muted/40 p-2.5">
              {/* The fact is about this record and stays; the instruction that followed it
                  only named the two buttons sitting underneath. */}
              <p className="text-xs text-muted-foreground">
                This project belongs to {project.owner_name ?? 'another salesperson'}.
              </p>
              <div className="flex flex-wrap gap-2">
                <Button type="button" size="sm" variant="outline" onClick={() => setRequesting('join')}>
                  Ask to join
                </Button>
                <Button type="button" size="sm" variant="ghost" onClick={() => setRequesting('dispute')}>
                  Dispute
                </Button>
              </div>
            </div>
          )}

          <div>
            <p className="text-xs text-muted-foreground">Open requests</p>
            {pending.length === 0 ? (
              <p className="text-sm text-muted-foreground">-</p>
            ) : (
              <ul className="mt-1 space-y-2">
                {pending.map((request) => (
                  <li key={request.id} className="rounded-md border border-border p-2.5">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Badge variant={request.kind === 'dispute' ? 'destructive' : 'secondary'}>
                        {request.kind === 'dispute' ? 'Dispute' : 'Join request'}
                      </Badge>
                      <span className="text-sm font-medium">
                        {request.requester_name ?? 'Someone'}
                      </span>
                    </div>
                    <p className="mt-1 break-words text-sm text-muted-foreground">
                      {request.reason}
                    </p>
                    {/* The server decides who may rule on this (owner for a join, a
                        manager for a dispute) and returns 403 otherwise, so the buttons
                        are offered rather than hidden behind a guessed-at rule. */}
                    <div className="mt-2 flex flex-wrap gap-2">
                      <Button
                        type="button"
                        size="sm"
                        disabled={decide.isPending}
                        onClick={() => decide.mutate({ id: request.id, approve: true })}
                      >
                        Approve
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        disabled={decide.isPending}
                        onClick={() => decide.mutate({ id: request.id, approve: false })}
                      >
                        Reject
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {decided.length > 0 && (
            <details className="text-sm">
              <summary className="cursor-pointer text-xs text-muted-foreground">
                Past decisions ({decided.length})
              </summary>
              <ul className="mt-2 space-y-2">
                {decided.map((request) => (
                  <li key={request.id} className="rounded-md border border-border p-2.5">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Badge variant="outline" className="capitalize">
                        {request.status}
                      </Badge>
                      <span className="text-xs text-muted-foreground">
                        {request.kind === 'dispute' ? 'Dispute' : 'Join'} by{' '}
                        {request.requester_name ?? 'someone'}
                        {request.decided_by_name ? ` · decided by ${request.decided_by_name}` : ''}
                      </span>
                    </div>
                    <p className="mt-1 break-words text-sm text-muted-foreground">
                      {request.reason}
                    </p>
                    {request.decision_note && (
                      <p className="mt-1 break-words text-xs text-muted-foreground">
                        Decision: {request.decision_note}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </CardContent>
      </Card>

      {requesting && (
        <RequestDialog
          project={project}
          kind={requesting}
          onDone={() => setRequesting(null)}
        />
      )}
    </>
  );
}

function RequestDialog({
  project,
  kind,
  onDone,
}: {
  project: Project;
  kind: 'join' | 'dispute';
  onDone: () => void;
}) {
  const [reason, setReason] = React.useState('');
  const { request } = useTakeoverMutations(project.id);
  const isJoin = kind === 'join';

  return (
    <Dialog open onOpenChange={(next) => !next && onDone()}>
      <DialogContent className="max-h-[92vh] w-full max-w-lg overflow-hidden">
        <DialogHeader>
          <DialogTitle>{isJoin ? 'Ask to join this project' : 'Dispute this project'}</DialogTitle>
          <DialogDescription>
            {isJoin
              ? `${project.owner_name ?? 'The owner'} decides. On approval you get edit rights.`
              : `A sales manager decides. On approval the project moves to you and ${project.owner_name ?? 'the current owner'} stays on as a collaborator.`}
          </DialogDescription>
        </DialogHeader>
        <form
          onSubmit={async (event) => {
            event.preventDefault();
            if (!reason.trim()) return;
            await request.mutateAsync({ kind, reason: reason.trim() });
            onDone();
          }}
        >
          <DialogBody className="max-h-[60vh] overflow-y-auto">
            <div className="space-y-1.5">
              <Label htmlFor="access-reason">
                Reason <span className="text-destructive">*</span>
              </Label>
              <Textarea
                id="access-reason"
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                rows={4}
                required
                placeholder={
                  isJoin
                    ? 'e.g. I hold the specifying architect relationship on this tender.'
                    : 'e.g. I registered this with the developer in March and have the meeting notes.'
                }
              />
            </div>
          </DialogBody>
          <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
            <Button type="button" variant="outline" onClick={onDone}>
              Cancel
            </Button>
            <Button type="submit" disabled={!reason.trim() || request.isPending}>
              {isJoin ? 'Send request' : 'Raise dispute'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
