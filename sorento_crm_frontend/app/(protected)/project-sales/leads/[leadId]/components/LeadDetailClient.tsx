'use client';

import * as React from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useSession } from 'next-auth/react';
import { RotateCcw, Ban, Check, Loader2, Pencil, Trash2, UserPlus, Users } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { useStatusGraph } from '@/app/(protected)/system-management/status-graphs/hooks/useStatusGraphs';
import {
  useCustomerPortfolio,
  useLead,
  useLeadMutations,
} from '../../../_shared/hooks/useProjects';
import { useLeadAcceptanceMutations } from '../../../_shared/hooks/useLeadAcceptance';
import type { LeadWithAcceptance } from '../../../_shared/types/leadAcceptance.types';
import { AssignLeadDialog } from '../../components/AssignLeadDialog';
import { DeclineLeadDialog } from '../../components/DeclineLeadDialog';
import { LeadAcceptanceBadge } from '../../components/LeadAcceptanceBadge';
import { canAssignLead, informantSourceLabel } from '../../components/acceptance';
import { DisqualifyLeadDialog } from './DisqualifyLeadDialog';
import { EditLeadInformantDialog } from './EditLeadInformantDialog';
import { QualifyLeadDialog } from './QualifyLeadDialog';

/**
 * One recorded sighting: who told us, what we heard, and what it became.
 *
 * The two terminal rungs are NOT in the status dropdown. Qualified and Disqualified are
 * reached through their own buttons because each does work the rung alone cannot: one
 * runs the registration clash check and creates a project, the other records a
 * reportable reason. The server refuses a bare move onto either, so the UI matching
 * that is honesty rather than duplication.
 */
export function LeadDetailClient({ leadId }: { leadId: string }) {
  const router = useRouter();
  const { data: lead, isLoading, isError, error } = useLead(leadId);
  const graph = useStatusGraph('project_lead', null, false);
  const { move, disqualify, reopen, remove, update } = useLeadMutations();
  const { assign, accept, decline } = useLeadAcceptanceMutations();
  const { data: session } = useSession();
  const [qualifying, setQualifying] = React.useState(false);
  const [disqualifying, setDisqualifying] = React.useState(false);
  const [assigning, setAssigning] = React.useState(false);
  const [declining, setDeclining] = React.useState(false);
  const [editingWho, setEditingWho] = React.useState(false);
  const [confirmDelete, setConfirmDelete] = React.useState(false);

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  if (isError || !lead) {
    return (
      <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-6 py-10 text-center">
        <h2 className="text-sm font-semibold text-destructive">
          This lead could not be loaded
        </h2>
        <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
          {error instanceof Error ? error.message : 'It may have been deleted.'}
        </p>
        <Button asChild variant="outline" className="mt-4">
          <Link href="/project-sales/leads">Back to leads</Link>
        </Button>
      </div>
    );
  }

  // Terminal rungs are excluded on purpose: they belong to the two actions.
  const statuses = (graph.data?.statuses ?? [])
    .filter((status) => status.is_active && !status.is_terminal)
    .sort((a, b) => a.sort_order - b.sort_order);

  const isOpen = lead.outcome === 'open';

  // Phase 1's ProjectLead predates the informant and the handshake, so the P1 fields are
  // read through the wider type. The dialogs below still take the phase-1 shape.
  const view: LeadWithAcceptance = lead;
  const viewerId = session?.user?.id;
  // Accept and decline belong to the person holding it. Anyone else pressing them would
  // get a 403, which is a worse way to learn the same thing.
  const isAssignee = Boolean(viewerId && view.owner_user_id === viewerId);
  const awaitingAcceptance = view.acceptance_state === 'assigned';
  // Shared with the leads list, so the row and this header can never disagree about
  // who is allowed to hand a lead on.
  const canAssign = canAssignLead(view);

  return (
    <div className="space-y-5">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 break-words">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-xs text-muted-foreground">{lead.lead_code}</span>
            <Badge variant={isOpen ? 'outline' : 'secondary'} className="capitalize">
              {lead.outcome}
            </Badge>
            {lead.status_label && (
              <Badge variant="secondary">{lead.status_label}</Badge>
            )}
            {!lead.can_edit && <Badge variant="outline">Read only</Badge>}
          </div>
          <h1 className="mt-1 text-xl font-semibold">{lead.title}</h1>
          <p className="text-sm text-muted-foreground">
            {[lead.developer_name, lead.location].filter(Boolean).join(' · ') ||
              'Nothing else recorded yet'}
          </p>
          <LeadAcceptanceBadge
            lead={view}
            className="mt-1.5 flex flex-wrap items-center gap-1.5"
          />
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {lead.can_edit && isOpen && awaitingAcceptance && isAssignee && (
            <>
              <Button
                type="button"
                disabled={accept.isPending}
                onClick={() => accept.mutate(lead.id)}
              >
                <Check className="size-4" aria-hidden />
                Accept
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={() => setDeclining(true)}
              >
                Decline
              </Button>
            </>
          )}
          {canAssign && (
            <Button type="button" variant="outline" onClick={() => setAssigning(true)}>
              <UserPlus className="size-4" aria-hidden />
              {view.owner_user_id ? 'Reassign' : 'Assign'}
            </Button>
          )}
          {isOpen && (
            <div className="w-full sm:w-48">
              <SearchableSelect
                value={lead.status_id ?? ''}
                onChange={(next) => {
                  if (!next || next === lead.status_id) return;
                  move.mutate({ id: lead.id, toStatusId: next });
                }}
                disabled={!lead.can_edit || move.isPending}
                options={statuses.map((status) => ({
                  value: status.id,
                  label: status.label,
                }))}
                placeholder="No stage set"
                aria-label="Lead stage"
              />
            </div>
          )}
          {lead.can_edit && isOpen && (
            <>
              <Button type="button" onClick={() => setQualifying(true)}>
                Qualify
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={() => setDisqualifying(true)}
              >
                <Ban className="size-4" aria-hidden />
                Disqualify
              </Button>
            </>
          )}
          {lead.can_edit && lead.outcome === 'disqualified' && (
            <Button
              type="button"
              variant="outline"
              disabled={reopen.isPending}
              onClick={() => reopen.mutate(lead.id)}
            >
              <RotateCcw className="size-4" aria-hidden />
              Reopen
            </Button>
          )}
          {lead.can_edit && (
            <Button
              type="button"
              variant="outline"
              onClick={() => setConfirmDelete(true)}
              aria-label="Delete lead"
            >
              <Trash2 className="size-4 text-destructive" aria-hidden />
              Delete
            </Button>
          )}
        </div>
      </header>

      {lead.possible_duplicates.length > 0 && (
        <div className="flex items-start gap-2 rounded-lg border border-border bg-muted/40 px-3 py-2.5 text-sm">
          <Users className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
          <p className="text-muted-foreground">
            {lead.possible_duplicates
              .map((hint) => hint.owner_name ?? hint.lead_code)
              .join(', ')}{' '}
            recorded this development too. Leads are not exclusive, so both stand. The
            first person to qualify it registers the project.
          </p>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <InformantCard
            lead={view}
            canEdit={lead.can_edit}
            onEdit={() => setEditingWho(true)}
          />

          <AcceptanceCard lead={view} />

          <Card>
            <CardHeader>
              <CardTitle className="text-sm">What we heard</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
                <Fact label="Developer" value={lead.developer_name} />
                <Fact label="Location" value={lead.location} />
                <Fact
                  label="Source"
                  value={lead.source ? lead.source.replace(/_/g, ' ') : null}
                />
                <Fact label="Who said what" value={lead.source_detail} />
                <Fact
                  label="Rough value"
                  value={lead.estimated_value ? formatMyr(lead.estimated_value) : null}
                />
                <Fact
                  label="Disqualified because"
                  value={
                    lead.disqualified_reason
                      ? lead.disqualified_reason.replace(/_/g, ' ')
                      : null
                  }
                />
              </dl>
              {lead.notes && (
                <p className="mt-4 break-words rounded-md bg-muted/60 px-3 py-2 text-sm">
                  {lead.notes}
                </p>
              )}
            </CardContent>
          </Card>

          <QualifiedProjects lead={view} />
        </div>

        <AccountPanel
          lead={view}
          canEdit={lead.can_edit}
          onSetBuyer={() => setEditingWho(true)}
        />
      </div>

      {qualifying && (
        <QualifyLeadDialog lead={lead} onDone={() => setQualifying(false)} />
      )}
      {disqualifying && (
        <DisqualifyLeadDialog
          lead={lead}
          onDone={() => setDisqualifying(false)}
          onConfirm={async (reason) => {
            await disqualify.mutateAsync({ id: lead.id, reason });
          }}
        />
      )}
      {assigning && (
        <AssignLeadDialog
          leadCode={lead.lead_code}
          currentOwnerName={lead.owner_name}
          submitting={assign.isPending}
          onDone={() => setAssigning(false)}
          onConfirm={async (ownerUserId, note) => {
            await assign.mutateAsync({ id: lead.id, ownerUserId, note });
          }}
        />
      )}
      {declining && (
        <DeclineLeadDialog
          leadCode={lead.lead_code}
          submitting={decline.isPending}
          onDone={() => setDeclining(false)}
          onConfirm={async (reason) => {
            await decline.mutateAsync({ id: lead.id, reason });
          }}
        />
      )}
      {editingWho && (
        <EditLeadInformantDialog
          lead={view}
          submitting={update.isPending}
          onDone={() => setEditingWho(false)}
          onConfirm={async (body) => {
            await update.mutateAsync({ id: lead.id, body });
          }}
        />
      )}

      <ConfirmDeleteDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="Confirm delete"
        description={`Delete ${lead.lead_code} "${lead.title}"? This action cannot be undone. Any project already registered from it is kept.`}
        onDelete={async () => {
          await remove.mutateAsync(lead.id);
        }}
        onSuccess={() => router.push('/project-sales/leads')}
        successMessage="Lead deleted"
      />

      {move.isPending && (
        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 className="size-3 animate-spin" aria-hidden />
          Moving stage…
        </p>
      )}
    </div>
  );
}

/**
 * Who told us. Its own card, above the buyer, so the two are never read as one thing:
 * an informant is a data source and never issues a purchase order.
 */
function InformantCard({
  lead,
  canEdit,
  onEdit,
}: {
  lead: LeadWithAcceptance;
  canEdit: boolean;
  onEdit: () => void;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-col items-start gap-2 sm:flex-row sm:items-center sm:justify-between">
        <CardTitle className="min-w-0 break-words text-sm">Who told us</CardTitle>
        {canEdit && (
          <Button type="button" variant="outline" size="sm" onClick={onEdit}>
            <Pencil className="size-4" aria-hidden />
            Edit
          </Button>
        )}
      </CardHeader>
      <CardContent>
        <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
          <Fact label="Source" value={informantSourceLabel(lead.informant_source)} />
          <Fact label="Their reference" value={lead.informant_ref} />
          <Fact
            label="Firm"
            value={lead.informant_party_label}
            emptyText="No firm on record"
          />
          <Fact label="Contact name" value={lead.informant_contact_name} />
          <Fact
            label="Buyer"
            value={lead.customer_name}
            emptyText="Not known yet"
          />
        </dl>
      </CardContent>
    </Card>
  );
}

/** The handshake: who holds it, since when, and what they said if they said no. */
function AcceptanceCard({ lead }: { lead: LeadWithAcceptance }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Handover</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <LeadAcceptanceBadge lead={lead} className="flex flex-wrap items-center gap-1.5" />
        <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
          <Fact label="Assigned to" value={lead.owner_name} emptyText="Nobody yet" />
          <Fact
            label="Assigned"
            value={
              lead.assigned_at ? formatDateTimeInMalaysia(lead.assigned_at) : null
            }
          />
          <Fact
            label="Accepted"
            value={
              lead.accepted_at ? formatDateTimeInMalaysia(lead.accepted_at) : null
            }
            emptyText="Not accepted yet"
          />
          <Fact
            label="Declined"
            value={
              lead.declined_at ? formatDateTimeInMalaysia(lead.declined_at) : null
            }
          />
          <Fact label="Declined because" value={lead.declined_reason} />
        </dl>
      </CardContent>
    </Card>
  );
}

/**
 * What this lead became. Always rendered, per the CRUD standard: an empty section with
 * a next step beats a section that vanishes and makes the feature look absent.
 */
function QualifiedProjects({ lead }: { lead: LeadWithAcceptance }) {
  const portfolio = useCustomerPortfolio(lead.customer_id ?? undefined);
  const projects = (portfolio.data?.projects ?? []).filter(
    (project) => project.lead_id === lead.id,
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Projects from this lead</CardTitle>
      </CardHeader>
      <CardContent>
        {portfolio.isLoading ? (
          <Skeleton className="h-12 w-full" />
        ) : projects.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            {lead.project_count > 0
              ? `${lead.project_count} project${lead.project_count === 1 ? '' : 's'} came from this lead. Open them from the pipeline.`
              : 'Nothing registered from this lead yet. Qualifying it runs the duplicate check and claims the development. One lead can yield several projects, so a masterplan can be split phase by phase.'}
          </p>
        ) : (
          <ul className="divide-y divide-border">
            {projects.map((project) => (
              <li key={project.id} className="flex items-center justify-between gap-2 py-2">
                <Link
                  href={`/project-sales/${project.id}`}
                  className="min-w-0 truncate text-sm text-primary hover:underline"
                  title={project.title}
                >
                  {project.project_code} · {project.title}
                </Link>
                <Badge variant="secondary" className="shrink-0 text-[11px]">
                  {project.status_label ?? project.outcome}
                </Badge>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

/** The account view (AC-O9), from the lead's side. */
function AccountPanel({
  lead,
  canEdit,
  onSetBuyer,
}: {
  lead: LeadWithAcceptance;
  canEdit: boolean;
  onSetBuyer: () => void;
}) {
  const portfolio = useCustomerPortfolio(lead.customer_id ?? undefined);
  const otherLeads = (portfolio.data?.leads ?? []).filter((row) => row.id !== lead.id);
  const projects = portfolio.data?.projects ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">
          {lead.customer_name ?? 'No buyer yet'}
        </CardTitle>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Everything this buyer has been part of, and what it turned into.
        </p>
      </CardHeader>
      <CardContent className="space-y-3">
        {!lead.customer_id ? (
          <div className="space-y-2">
            <p className="text-xs text-muted-foreground">
              A buyer is named once a contractor is awarded.
            </p>
            {canEdit && (
              <Button type="button" variant="outline" size="sm" onClick={onSetBuyer}>
                Set the buyer
              </Button>
            )}
          </div>
        ) : portfolio.isLoading ? (
          <Skeleton className="h-24 w-full" />
        ) : (
          <>
            <div>
              <p className="text-xs font-medium">Other leads</p>
              {otherLeads.length === 0 ? (
                <p className="text-xs text-muted-foreground">
                  This is their only lead so far.
                </p>
              ) : (
                <ul className="mt-1 space-y-1">
                  {otherLeads.slice(0, 6).map((row) => (
                    <li key={row.id} className="truncate text-xs">
                      <Link
                        href={`/project-sales/leads/${row.id}`}
                        className="text-primary hover:underline"
                        title={row.title}
                      >
                        {row.lead_code} · {row.title}
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div>
              <p className="text-xs font-medium">Projects</p>
              {projects.length === 0 ? (
                <p className="text-xs text-muted-foreground">
                  Nothing registered against this account yet.
                </p>
              ) : (
                <ul className="mt-1 space-y-1">
                  {projects.slice(0, 6).map((project) => (
                    <li key={project.id} className="truncate text-xs">
                      <Link
                        href={`/project-sales/${project.id}`}
                        className="text-primary hover:underline"
                        title={project.title}
                      >
                        {project.project_code} · {project.title}
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function Fact({
  label,
  value,
  emptyText = 'Not recorded',
}: {
  label: string;
  value?: string | null;
  emptyText?: string;
}) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="break-words text-sm">
        {value ?? <span className="text-muted-foreground">{emptyText}</span>}
      </dd>
    </div>
  );
}

function formatMyr(value: string): string {
  const amount = Number(value);
  if (Number.isNaN(amount)) return value;
  return `RM ${amount.toLocaleString('en-MY', { maximumFractionDigits: 2 })}`;
}
