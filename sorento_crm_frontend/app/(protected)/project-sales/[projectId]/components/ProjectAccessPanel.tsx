'use client';

import * as React from 'react';
import { useQuery } from '@tanstack/react-query';
import { Crown, Star, UserCog, UserPlus, X, type LucideIcon } from 'lucide-react';
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
import { cn } from '@/lib/utils';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import type { RecordAction } from '@/components/common/recordActions';
import { RowActionsMenu } from '@/components/common/RowActionsMenu';
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
import { useIsMobile } from '@/hooks/use-mobile';
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
  // A phone shows the Salesperson (with its role icons) and the "..." column: Date, How they
  // found it and Status stay one Columns click away (B4).
  const narrow = useIsMobile();
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

  // By person, not by row: the owner can also hold a secondary-lead row that is not the one
  // marked Owner, and it must not offer "Reassign to <owner>".
  const ownerUserId = project.owner_user_id;
  // The mutation's own fields, not the result object (a new one every render): the grid's
  // columns depend on this builder, and a new column set every render remounts the open "...".
  const { mutate: decideMutate, isPending: deciding } = decide;
  /**
   * THE row actions, for a manager only: the "..." menu and the right-click menu both render
   * this array, so neither can offer something the other does not.
   */
  const leadRowActions = React.useCallback(
    (row: ProjectLeadRow): RecordAction[] => {
      if (!canManage) return [];
      const actions: RecordAction[] = [];
      if (row.userId !== ownerUserId && !row.inactive) {
        actions.push({
          key: 'project_lead.reassign',
          label: `Reassign to ${row.name}`,
          icon: UserCog,
          run: () => setReassignTo(row.userId),
        });
      }
      if (row.status === 'pending' && row.requestId) {
        const requestId = row.requestId;
        actions.push({
          key: 'project_lead.dismiss',
          label: 'Dismiss',
          icon: X,
          disabled: deciding,
          run: () => decideMutate({ id: requestId, approve: false }),
        });
      }
      return actions;
    },
    [canManage, ownerUserId, decideMutate, deciding],
  );

  // Sizes are the grid's minimum width; a wider card stretches them in proportion. A phone shows
  // Salesperson and "..." (248px, the card is about 299px there); Status keeps room for the whole
  // Dismissed pill, and all five (688px) stretch to fill the card on a desktop.
  const columns = React.useMemo<ColumnDef<ProjectLeadRow>[]>(
    () => [
      {
        id: 'name',
        accessorFn: (row) => row.name,
        header: ({ column }) => <DataGridColumnHeader title="Salesperson" column={column} />,
        cell: ({ row }) => {
          const lead = row.original;
          const name = lead.inactive ? `${lead.name} (inactive)` : lead.name;
          // One line: the name truncates, the role icons after it never do.
          return (
            <div className="flex min-w-0 items-center gap-1.5">
              <span className="truncate text-sm font-medium" title={name}>
                {name}
              </span>
              {lead.lead === 'Primary' && (
                // The Stakeholders tab's primary-contact star, same look.
                <RoleIcon icon={Star} label="Primary" iconClassName="fill-amber-400 text-amber-500" />
              )}
              {lead.lead === 'Secondary' && <RoleIcon icon={UserPlus} label="Secondary" />}
              {lead.isOwner && <RoleIcon icon={Crown} label="Owner" />}
            </div>
          );
        },
        size: 200,
        meta: { headerTitle: 'Salesperson' },
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
        size: 96,
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
        size: 240,
        meta: { headerTitle: 'How they found it' },
      },
      {
        id: 'status',
        accessorFn: (row) => row.status ?? '',
        header: ({ column }) => <DataGridColumnHeader title="Status" column={column} />,
        cell: ({ row }) => {
          const status = row.original.status;
          if (!status) return null;
          return (
            <Badge variant={status === 'pending' ? 'warning' : 'secondary'} appearance="light" size="sm">
              {status === 'pending' ? 'Pending' : 'Dismissed'}
            </Badge>
          );
        },
        size: 104,
        meta: { headerTitle: 'Status' },
      },
      ...(canManage
        ? [
            {
              id: 'actions',
              header: () => null,
              enableSorting: false,
              enableHiding: false,
              cell: ({ row }: { row: { original: ProjectLeadRow } }) => (
                <RowActionsMenu actions={leadRowActions(row.original)} ariaLabel={row.original.name} />
              ),
              size: 48,
              // Grid chrome, not a column a reader reorders: no drag grip on its header.
              meta: { draggable: false },
            } satisfies ColumnDef<ProjectLeadRow>,
          ]
        : []),
    ],
    [canManage, leadRowActions],
  );

  const rowAt = (target: EventTarget) => {
    const id = (target as Element).closest?.('[data-lead-row-id]')?.getAttribute('data-lead-row-id');
    return id ? leads.find((row) => row.id === id) : undefined;
  };
  /** The row under the pointer, when it has anything to offer this user; else undefined. */
  const menuRowAt = (target: EventTarget) => {
    const hit = rowAt(target);
    return hit && leadRowActions(hit).length > 0 ? hit : undefined;
  };

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

          {/* Managers only: the right-click menu (long-press on touch) and the row's "..."
              (owner, 14 Nov hand test) both render leadRowActions, the one action list. */}
          <ContextMenu modal={false}>
            <ContextMenuTrigger asChild>
              <div
                // Capture phase: a right-click with nothing to offer stops here, so the
                // browser's own menu shows instead of an empty one.
                onContextMenuCapture={(event) => {
                  const hit = menuRowAt(event.target);
                  if (!hit) {
                    event.stopPropagation();
                    return;
                  }
                  setMenuRow(hit);
                }}
                onPointerDownCapture={(event) => {
                  if (event.pointerType !== 'mouse') setMenuRow(menuRowAt(event.target) ?? null);
                }}
              >
                <PanelDataGrid<ProjectLeadRow>
                  // Column visibility is read at mount, so the grid remounts once the width is known.
                  key={narrow ? 'narrow' : 'wide'}
                  initialColumnVisibility={
                    narrow ? { date: false, found_by: false, status: false } : undefined
                  }
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
              {menuRow &&
                leadRowActions(menuRow).map((action) => (
                  <ContextMenuItem
                    key={action.key}
                    disabled={action.disabled}
                    onSelect={() => void action.run()}
                  >
                    {action.icon && <action.icon className="size-4" aria-hidden />}
                    {action.label}
                  </ContextMenuItem>
                ))}
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

/** A role next to a salesperson's name (Primary, Secondary, Owner): an icon named by its word. */
function RoleIcon({
  icon: Icon,
  label,
  iconClassName,
}: {
  icon: LucideIcon;
  label: string;
  iconClassName?: string;
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          role="img"
          aria-label={label}
          tabIndex={0}
          className="inline-flex shrink-0 text-muted-foreground"
        >
          <Icon className={cn('size-3.5', iconClassName)} aria-hidden />
        </span>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
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
