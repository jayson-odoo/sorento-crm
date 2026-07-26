'use client';

import * as React from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Flame, Loader2, Trash2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { useStatusGraph } from '@/app/(protected)/system-management/status-graphs/hooks/useStatusGraphs';
import {
  useChangeProjectStatus,
  useDeleteProject,
  useProject,
} from '../../_shared/hooks/useProjects';
import { CriticalPanel } from './CriticalPanel';
import { ProjectAccessPanel } from './ProjectAccessPanel';
import { StakeholdersPanel } from './StakeholdersPanel';
import { TasksPanel } from './TasksPanel';

/**
 * Project detail as URL-routed tabs (AC-G6).
 *
 * Every tab renders even when it has nothing in it, with an explicit next step. A tab
 * that disappears when empty makes the feature look absent rather than unused, and the
 * user cannot discover what they are supposed to do next.
 *
 * Tabs whose slice has not shipped say so plainly instead of pretending: an honest
 * "arrives with quotations" beats a stub that looks broken.
 */
const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'stakeholders', label: 'Stakeholders' },
  { id: 'tasks', label: 'Tasks' },
  { id: 'quotations', label: 'Quotations' },
  { id: 'samples', label: 'Samples' },
  { id: 'sponsorships', label: 'Sponsorships' },
  { id: 'pos', label: 'POs' },
  { id: 'activity', label: 'Activity' },
  { id: 'documents', label: 'Documents' },
] as const;

type TabId = (typeof TABS)[number]['id'];

export function ProjectDetailClient({ projectId }: { projectId: string }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const requestedTab = searchParams.get('tab') as TabId | null;
  const activeTab: TabId =
    requestedTab && TABS.some((tab) => tab.id === requestedTab) ? requestedTab : 'overview';

  const { data: project, isLoading, isError, error } = useProject(projectId);
  const graph = useStatusGraph('project', project?.template_id ?? null, false);
  const move = useChangeProjectStatus();
  const remove = useDeleteProject();
  const [confirmDelete, setConfirmDelete] = React.useState(false);

  function selectTab(tab: TabId) {
    const next = new URLSearchParams(searchParams.toString());
    if (tab === 'overview') next.delete('tab');
    else next.set('tab', tab);
    const query = next.toString();
    router.replace(`/project-sales/${projectId}${query ? `?${query}` : ''}`, {
      scroll: false,
    });
  }

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (isError || !project) {
    return (
      <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-6 py-10 text-center">
        <h2 className="text-sm font-semibold text-destructive">
          This project could not be loaded
        </h2>
        <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
          {error instanceof Error ? error.message : 'It may have been deleted.'}
        </p>
        <Button asChild variant="outline" className="mt-4">
          <Link href="/project-sales/pipeline">Back to the pipeline</Link>
        </Button>
      </div>
    );
  }

  const statuses = (graph.data?.statuses ?? [])
    .filter((status) => status.is_active)
    .sort((a, b) => a.sort_order - b.sort_order);

  return (
    <div className="space-y-5">
      {/* flex-col until sm: a long title and the action buttons cannot share a row at
          phone width without overlapping and forcing page-wide horizontal overflow. */}
      <header className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 break-words">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-xs text-muted-foreground">
              {project.project_code}
            </span>
            <Badge variant={project.outcome === 'open' ? 'outline' : 'secondary'} className="capitalize">
              {project.outcome}
            </Badge>
            {project.is_critical && (
              <Badge variant="destructive" className="gap-1">
                <Flame className="size-3" aria-hidden />
                Critical
              </Badge>
            )}
            {!project.can_edit && <Badge variant="outline">Read only</Badge>}
          </div>
          <h1 className="mt-1 text-xl font-semibold">{project.title}</h1>
          <p className="text-sm text-muted-foreground">
            {[project.developer_name, project.location].filter(Boolean).join(' · ') ||
              'No developer or location recorded yet'}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="w-full sm:w-56">
            <SearchableSelect
              value={project.status_id ?? ''}
              onChange={(next) => {
                if (!next || next === project.status_id) return;
                move.mutate({ projectId: project.id, toStatusId: next });
              }}
              disabled={!project.can_edit || move.isPending}
              options={statuses.map((status) => ({
                value: status.id,
                label: status.label,
              }))}
              placeholder="No stage set"
              aria-label="Project stage"
            />
          </div>
          {project.can_edit && (
            <Button
              type="button"
              variant="outline"
              onClick={() => setConfirmDelete(true)}
              aria-label="Delete project"
            >
              <Trash2 className="size-4 text-destructive" aria-hidden />
              Delete
            </Button>
          )}
        </div>
      </header>

      {/* Horizontal scroll on the tab strip only, so nine tabs never make the page
          itself scroll sideways. */}
      <nav
        className="-mx-1 flex gap-1 overflow-x-auto border-b border-border px-1"
        aria-label="Project sections"
      >
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => selectTab(tab.id)}
            aria-current={activeTab === tab.id ? 'page' : undefined}
            className={
              activeTab === tab.id
                ? 'shrink-0 border-b-2 border-primary px-3 py-2 text-sm font-medium text-foreground'
                : 'shrink-0 border-b-2 border-transparent px-3 py-2 text-sm text-muted-foreground hover:text-foreground'
            }
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {activeTab === 'overview' && (
        <div className="grid gap-4 lg:grid-cols-3">
          <div className="space-y-4 lg:col-span-2">
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">Registration</CardTitle>
              </CardHeader>
              <CardContent>
                <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
                  <Fact label="Developer" value={project.developer_name} />
                  <Fact label="Registered company / SPV" value={project.registered_company_name} />
                  <Fact label="Project type" value={project.type_name} />
                  <Fact label="Template" value={project.template_name} />
                  <Fact label="Location" value={project.location} />
                  <Fact label="Architect" value={project.architect_name} />
                  <Fact label="Main contractor" value={project.main_contractor_name} />
                  <Fact
                    label="Estimated sales value"
                    value={
                      project.estimated_sales_value
                        ? formatMyr(project.estimated_sales_value)
                        : null
                    }
                  />
                  <Fact label="Launch date" value={formatDate(project.launch_date)} />
                  <Fact
                    label="Expected delivery"
                    value={
                      project.expected_delivery_from || project.expected_delivery_to
                        ? `${formatDate(project.expected_delivery_from) ?? '?'} to ${formatDate(project.expected_delivery_to) ?? '?'}`
                        : null
                    }
                  />
                  <Fact label="Owner" value={project.owner_name} />
                  <Fact
                    label="Brands"
                    value={project.brands.length ? project.brands.join(', ') : null}
                  />
                </dl>

                {/* AC-O10. "Registered directly" is a real answer, not a missing one:
                    a tender notice claimed the same hour never had a lead. */}
                <div className="mt-4 border-t border-border pt-3">
                  <p className="text-xs text-muted-foreground">Came from</p>
                  {project.lead_id ? (
                    <p className="text-sm">
                      <Link
                        href={`/project-sales/leads/${project.lead_id}`}
                        className="text-primary hover:underline"
                      >
                        Lead {project.lead_code}
                      </Link>
                      {project.lead_source
                        ? ` · ${project.lead_source.replace(/_/g, ' ')}`
                        : ''}
                      {project.lead_created_at
                        ? ` · recorded ${formatDate(project.lead_created_at)}`
                        : ''}
                    </p>
                  ) : (
                    <p className="text-sm text-muted-foreground">
                      Registered directly, with no prior lead.
                    </p>
                  )}
                </div>
              </CardContent>
            </Card>

            <CriticalPanel project={project} />
          </div>

          <div className="space-y-4">
            <ProjectAccessPanel project={project} />
          </div>
        </div>
      )}

      {activeTab === 'stakeholders' && <StakeholdersPanel project={project} />}

      {activeTab === 'tasks' && <TasksPanel project={project} />}
      {activeTab === 'quotations' && (
        <NotYetPanel
          title="Quotations"
          body="Quotation versions, the price floor guardrail and the won/lost outcome per scope arrive with the quotations slice."
        />
      )}
      {activeTab === 'samples' && (
        <NotYetPanel
          title="Sample submissions"
          body="Samples bind to a quotation version, so they arrive after quotations."
        />
      )}
      {activeTab === 'sponsorships' && (
        <NotYetPanel
          title="Sponsorships"
          body="Sponsorship forms are recorded today as free text. Linking them to this project arrives with the sponsorship slice, including the transition period where both the free-text and the picker versions of the form work."
        />
      )}
      {activeTab === 'pos' && (
        <NotYetPanel
          title="Project purchase orders"
          body="A customer's PO against this project is recorded separately from supplier purchase orders. Once any PO exists here, this project can be archived but not deleted."
        />
      )}
      {activeTab === 'activity' && (
        <NotYetPanel
          title="Activity"
          body="The shared activity feed, mentions and internal notes plug in through the existing activities registry. Meaningful activity is what the staleness nudges read, so it lands with the follow-up slice."
        />
      )}
      {activeTab === 'documents' && (
        <NotYetPanel
          title="Documents"
          body="Tender documents and drawings attach through the shared attachment directory, with Photo-typed attachments feeding the quotation line images."
        />
      )}

      <ConfirmDeleteDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="Confirm delete"
        description={`Delete ${project.project_code} "${project.title}"? This action cannot be undone. If a customer purchase order has been recorded against it, archive it instead.`}
        onDelete={async () => {
          await remove.mutateAsync(project.id);
        }}
        onSuccess={() => router.push('/project-sales/pipeline')}
        successMessage="Project deleted"
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

function Fact({ label, value }: { label: string; value?: string | null }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="break-words text-sm">
        {value ?? <span className="text-muted-foreground">Not recorded</span>}
      </dd>
    </div>
  );
}

function NotYetPanel({ title, body }: { title: string; body: string }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="max-w-2xl text-sm text-muted-foreground">{body}</p>
      </CardContent>
    </Card>
  );
}

function formatMyr(value: string): string {
  const amount = Number(value);
  if (Number.isNaN(amount)) return value;
  return `RM ${amount.toLocaleString('en-MY', { maximumFractionDigits: 2 })}`;
}

function formatDate(iso?: string | null): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString('en-MY', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  });
}
