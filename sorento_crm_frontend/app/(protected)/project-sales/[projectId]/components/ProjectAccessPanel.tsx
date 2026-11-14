'use client';

import * as React from 'react';
import { useQuery } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { SectionSkeleton } from '@/components/common/SectionSkeleton';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuTrigger,
} from '@/components/ui/context-menu';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { useHasPermission } from '@/hooks/usePermissions';
import { formatDateInMalaysia } from '@/lib/helpers';
import {
  useCollaborators,
  useTakeoverMutations,
  useTakeoverRequests,
} from '../../_shared/hooks/useProjects';
import type { ColumnDef } from '@tanstack/react-table';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { PanelDataGrid } from '@/components/common/PanelDataGrid';
import { getUserLookup } from '@/services/userSelectService';
import type { Project } from '../../_shared/types/project.types';
import { isProjectApproved } from '../../_shared/lib/projectApproval';
import { projectCodeLabel } from '../../_shared/lib/projectCode';
import { buildProjectLeads, type ProjectLeadRow } from '../../_shared/lib/projectLeads';
import { useLeadSourceLabel } from '../../_shared/hooks/useLeadSourceLabel';
import { ReassignProjectDialog } from './ReassignProjectDialog';

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
  const canManage = useHasPermission('projects.projects.manage');
  const [requesting, setRequesting] = React.useState<'join' | 'dispute' | null>(null);
  const [menuRow, setMenuRow] = React.useState<ProjectLeadRow | null>(null);
  const [reassignTo, setReassignTo] = React.useState<string | null>(null);
  const sourceLabel = useLeadSourceLabel(project.lead_source);
  // The same active-people list the reassign dialog picks from: someone missing from it is
  // inactive, so their row says so and offers no Reassign.
  const people = useQuery({
    queryKey: ['user-lookup', 'project-owner'],
    queryFn: () => getUserLookup(),
  });
  const activeUserIds = React.useMemo(
    () =>
      Array.isArray(people.data) && people.data.length > 0
        ? new Set(people.data.map((person) => person.id))
        : null,
    [people.data],
  );

  // Every lead on the project in one list: the primary, every secondary lead (a dispute
  // request, pending or decided), and the current owner when they are neither. Join requests
  // stay under Open requests for the owner to rule on.
  const leads = React.useMemo(
    () => buildProjectLeads(project, requests.data ?? [], sourceLabel, activeUserIds),
    [project, requests.data, sourceLabel, activeUserIds],
  );
  const pending = (requests.data ?? []).filter(
    (request) => request.status === 'pending' && request.kind !== 'dispute',
  );
  const decided = (requests.data ?? []).filter(
    (request) => request.status !== 'pending' && request.kind !== 'dispute',
  );

  const columns = React.useMemo<ColumnDef<ProjectLeadRow>[]>(
    () => [
      {
        id: 'name',
        accessorFn: (row) => row.name,
        header: ({ column }) => <DataGridColumnHeader title="Salesperson" column={column} />,
        cell: ({ row }) => {
          const name = row.original.inactive ? `${row.original.name} (inactive)` : row.original.name;
          return (
            <span className="block truncate text-sm font-medium" title={name}>
              {name}
            </span>
          );
        },
        size: 64,
        meta: { headerTitle: 'Salesperson' },
      },
      {
        id: 'lead',
        accessorFn: (row) => row.lead ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Lead" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate text-sm" title={row.original.lead ?? undefined}>
            {row.original.lead ?? ''}
          </span>
        ),
        size: 44,
        meta: { headerTitle: 'Lead' },
      },
      {
        id: 'date',
        accessorFn: (row) => row.date ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Date" column={column} />,
        cell: ({ row }) => {
          const date = row.original.date ? formatDateInMalaysia(row.original.date) : '-';
          return (
            <span className="block truncate text-sm" title={date}>
              {date}
            </span>
          );
        },
        size: 52,
        meta: { headerTitle: 'Date' },
      },
      {
        id: 'found_by',
        accessorFn: (row) => row.foundBy ?? '',
        header: ({ column }) => <DataGridColumnHeader title="How they found it" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate text-sm" title={row.original.foundBy ?? undefined}>
            {row.original.foundBy ?? '-'}
          </span>
        ),
        size: 76,
        meta: { headerTitle: 'How they found it' },
      },
      {
        id: 'owner',
        accessorFn: (row) => (row.isOwner ? 'Yes' : ''),
        header: ({ column }) => <DataGridColumnHeader title="Owner" column={column} />,
        cell: ({ row }) => (
          <span className="block truncate text-sm">{row.original.isOwner ? 'Yes' : ''}</span>
        ),
        size: 28,
        meta: { headerTitle: 'Owner' },
      },
      {
        id: 'status',
        accessorFn: (row) => row.status ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        cell: ({ row }) => {
          const status = row.original.status;
          if (!status) return null;
          return (
            <Badge variant={status === 'pending' ? 'warning' : 'secondary'} appearance="light">
              {status === 'pending' ? 'Pending' : 'Dismissed'}
            </Badge>
          );
        },
        size: 36,
        meta: { headerTitle: 'Status' },
      },
    ],
    [],
  );

  const rowAt = (target: EventTarget) => {
    const id = (target as Element).closest?.('[data-lead-row-id]')?.getAttribute('data-lead-row-id');
    return id ? leads.find((row) => row.id === id) : undefined;
  };
  const canReassignTo = (row: ProjectLeadRow) => !row.isOwner && !row.inactive;
  const hasMenu = (row: ProjectLeadRow) =>
    canManage && (canReassignTo(row) || row.status === 'pending');

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
              <SectionSkeleton rows={2} className="mt-1" />
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

          {/* No join or dispute on a registration that is not a project yet (security N3). */}
          {!project.can_edit && isProjectApproved(project) && (
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
                  Register as secondary lead
                </Button>
              </div>
            </div>
          )}

          {/* The row actions are its right-click menu (long-press on touch), managers only:
              no buttons on the rows (owner: right-click over icons). */}
          <ContextMenu modal={false}>
            <ContextMenuTrigger asChild>
              <div
                // Capture phase: a right-click with nothing to offer stops here, so the
                // browser's own menu shows instead of an empty one.
                onContextMenuCapture={(event) => {
                  const hit = rowAt(event.target);
                  if (!hit || !hasMenu(hit)) {
                    event.stopPropagation();
                    return;
                  }
                  setMenuRow(hit);
                }}
                onPointerDownCapture={(event) => {
                  if (event.pointerType !== 'mouse') setMenuRow(rowAt(event.target) ?? null);
                }}
              >
                <PanelDataGrid<ProjectLeadRow>
                  columns={columns}
                  rows={leads}
                  getRowId={(row) => row.id}
                  listingKey="projects.projects.view::project-leads"
                  isLoading={requests.isLoading}
                  error={requests.isError ? requests.error : undefined}
                  onRetry={() => void requests.refetch()}
                  rowAttributes={(row) => ({ 'data-lead-row-id': row.id })}
                  sortable
                  emptyTitle="No leads"
                />
              </div>
            </ContextMenuTrigger>
            <ContextMenuContent className="w-56" hidden={!menuRow}>
              {menuRow && canManage && (
                <>
                  {canReassignTo(menuRow) && (
                    <ContextMenuItem onSelect={() => setReassignTo(menuRow.userId)}>
                      Reassign to {menuRow.name}
                    </ContextMenuItem>
                  )}
                  {menuRow.status === 'pending' && menuRow.requestId && (
                    <ContextMenuItem
                      disabled={decide.isPending}
                      onSelect={() => decide.mutate({ id: menuRow.requestId!, approve: false })}
                    >
                      Dismiss
                    </ContextMenuItem>
                  )}
                </>
              )}
            </ContextMenuContent>
          </ContextMenu>

          <div>
            <p className="text-xs text-muted-foreground">Open requests</p>
            {pending.length === 0 ? (
              <p className="text-sm text-muted-foreground">-</p>
            ) : (
              <ul className="mt-1 space-y-2">
                {pending.map((request) => (
                  <li key={request.id} className="rounded-md border border-border p-2.5">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Badge variant="secondary">Join request</Badge>
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
                        Join by{' '}
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

      {reassignTo && (
        <ReassignProjectDialog
          project={project}
          initialUserId={reassignTo}
          onDone={() => setReassignTo(null)}
        />
      )}

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
          <DialogTitle>
            {isJoin ? 'Ask to join this project' : `Register as secondary lead on ${projectCodeLabel(project)}`}
          </DialogTitle>
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
                {isJoin ? 'Reason' : 'How and when did you find this project?'}{' '}
                <span className="text-destructive">*</span>
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
              {isJoin ? 'Send request' : 'Register as secondary lead'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
