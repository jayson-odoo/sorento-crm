'use client';

import * as React from 'react';
import type { PaginationState, SortingState } from '@tanstack/react-table';
import { Plus, Search, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { useLeadMutations, useLeads } from '../../_shared/hooks/useProjects';
import { useLeadAcceptanceMutations } from '../../_shared/hooks/useLeadAcceptance';
import type { LeadWithAcceptance } from '../../_shared/types/leadAcceptance.types';
import { AssignLeadDialog } from './AssignLeadDialog';
import { LeadsGrid } from './LeadsGrid';
import { LeadWizardDialog } from './LeadWizardDialog';

const OUTCOME_OPTIONS = [
  { value: 'open', label: 'Open' },
  { value: 'qualified', label: 'Qualified' },
  { value: 'disqualified', label: 'Disqualified' },
];

const SOURCE_OPTIONS = [
  { value: 'site_visit', label: 'Site visit' },
  { value: 'architect', label: 'Architect' },
  { value: 'contractor', label: 'Contractor' },
  { value: 'dealer', label: 'Dealer' },
  { value: 'inbound', label: 'Inbound enquiry' },
  { value: 'other', label: 'Other' },
];

/**
 * Leads: what we have heard about, before anybody owns it.
 *
 * Defaults to OPEN leads because the list is a worklist, not an archive: a qualified
 * lead's real life continues on its project, and a disqualified one is history. Both
 * stay one filter click away rather than being hidden.
 *
 * The rows are the shared DataGrid, the same one every other list in the product uses.
 * Search, the two filters and Export all live on that grid's ONE toolbar row rather than
 * in a bespoke bar above it, so this screen is read exactly like the users list, the
 * pipeline and the acceptance worklist.
 *
 * There are no summary tiles above the grid. Conversion is a reporting question and it
 * is answered on the reports screen; on a worklist it pushed the rows below the fold to
 * say something nobody came here to read.
 */
export function LeadsClient() {
  const [wizardOpen, setWizardOpen] = React.useState(false);
  const [search, setSearch] = React.useState('');
  const [debounced, setDebounced] = React.useState('');
  const [outcome, setOutcome] = React.useState('open');
  const [source, setSource] = React.useState('');
  const [pagination, setPagination] = React.useState<PaginationState>({
    pageIndex: 0,
    pageSize: 25,
  });
  const [sorting, setSorting] = React.useState<SortingState>([
    { id: 'created_at', desc: true },
  ]);
  const [assignTarget, setAssignTarget] = React.useState<LeadWithAcceptance | null>(null);
  const [deleteTarget, setDeleteTarget] = React.useState<LeadWithAcceptance | null>(null);

  const { assign } = useLeadAcceptanceMutations();
  const { remove } = useLeadMutations();

  React.useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(search.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [search]);

  // Narrowing the set changes which rows exist, so page 3 of the old set is a page of
  // nothing in the new one.
  React.useEffect(() => {
    setPagination((previous) => ({ ...previous, pageIndex: 0 }));
  }, [debounced, outcome, source]);

  const leads = useLeads({
    query: debounced || undefined,
    outcome: outcome ? [outcome] : undefined,
    source: source ? [source] : undefined,
    page: pagination.pageIndex + 1,
    limit: pagination.pageSize,
    sort: sorting[0]?.id ?? 'created_at',
    dir: (sorting[0]?.desc ?? true) ? 'desc' : 'asc',
  });
  // The lead list already serves the P1 informant and acceptance fields; phase 1's
  // ProjectLead type predates them, so the rows are read through the wider type.
  const rows: LeadWithAcceptance[] = leads.data?.data ?? [];
  const total = leads.data?.pagination.total ?? 0;

  const filtered = Boolean(debounced || source || outcome !== 'open');
  const activeFilterCount = (outcome !== 'open' ? 1 : 0) + (source ? 1 : 0);

  const searchSlot = (
    <div className="relative w-full max-w-xs">
      <Search
        className="pointer-events-none absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
        aria-hidden
      />
      <Input
        value={search}
        onChange={(event) => setSearch(event.target.value)}
        placeholder="Search title or lead code…"
        className="ps-9"
        aria-label="Search leads"
      />
      {search && (
        <Button
          mode="icon"
          variant="dim"
          className="absolute end-1.5 top-1/2 h-6 w-6 -translate-y-1/2"
          onClick={() => setSearch('')}
          aria-label="Clear search"
        >
          <X />
        </Button>
      )}
    </div>
  );

  return (
    <div className="space-y-5">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 break-words">
          <h1 className="text-xl font-semibold">Leads</h1>
          <p className="text-sm text-muted-foreground">
            Developments we have heard about. Nobody owns one until a salesperson
            accepts it.
          </p>
        </div>
        <Button type="button" onClick={() => setWizardOpen(true)}>
          <Plus className="size-4" aria-hidden />
          Record a lead
        </Button>
      </header>

      {leads.isError ? (
        <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-6 py-10 text-center">
          <h2 className="text-sm font-semibold text-destructive">
            Leads could not be loaded
          </h2>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
            {leads.error instanceof Error ? leads.error.message : 'Try again shortly.'}
          </p>
          <Button
            type="button"
            variant="outline"
            className="mt-4"
            onClick={() => void leads.refetch()}
          >
            Try again
          </Button>
        </div>
      ) : (
        <LeadsGrid
          leads={rows}
          total={total}
          isLoading={leads.isLoading}
          isFetching={leads.isFetching}
          pagination={pagination}
          onPaginationChange={setPagination}
          sorting={sorting}
          onSortingChange={setSorting}
          onRefresh={() => void leads.refetch()}
          searchSlot={searchSlot}
          onAssign={setAssignTarget}
          onDelete={setDeleteTarget}
          filters={{
            kind: 'custom',
            active: activeFilterCount > 0,
            activeCount: activeFilterCount,
            content: (
              <div className="space-y-3">
                <div className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground">Outcome</Label>
                  <SearchableSelect
                    value={outcome}
                    onChange={setOutcome}
                    clearable
                    options={OUTCOME_OPTIONS}
                    placeholder="All outcomes"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground">Source</Label>
                  <SearchableSelect
                    value={source}
                    onChange={setSource}
                    clearable
                    options={SOURCE_OPTIONS}
                    placeholder="All sources"
                  />
                </div>
                {activeFilterCount > 0 && (
                  <Button
                    variant="outline"
                    size="sm"
                    className="w-full"
                    onClick={() => {
                      setOutcome('open');
                      setSource('');
                    }}
                  >
                    Back to open leads
                  </Button>
                )}
              </div>
            ),
          }}
          emptyState={
            <div className="px-6 py-10 text-center">
              <p className="text-sm font-semibold">
                {filtered ? 'No leads match these filters' : 'No open leads'}
              </p>
              <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                Record what you heard on site, even when it is vague. A lead costs
                nothing and claims nothing: it becomes somebody&apos;s only when they
                accept it.
              </p>
              <Button type="button" className="mt-4" onClick={() => setWizardOpen(true)}>
                <Plus className="size-4" aria-hidden />
                Record a lead
              </Button>
            </div>
          }
        />
      )}

      {wizardOpen && <LeadWizardDialog onDone={() => setWizardOpen(false)} />}

      {assignTarget && (
        <AssignLeadDialog
          leadCode={assignTarget.lead_code}
          currentOwnerName={assignTarget.owner_name}
          submitting={assign.isPending}
          onDone={() => setAssignTarget(null)}
          onConfirm={async (ownerUserId, note) => {
            await assign.mutateAsync({ id: assignTarget.id, ownerUserId, note });
          }}
        />
      )}

      <ConfirmDeleteDialog
        open={Boolean(deleteTarget)}
        onOpenChange={(next) => !next && setDeleteTarget(null)}
        title="Confirm delete"
        description={
          deleteTarget
            ? `Delete ${deleteTarget.lead_code} "${deleteTarget.title}"? This action cannot be undone. Any project already registered from it is kept.`
            : ''
        }
        onDelete={async () => {
          if (deleteTarget) await remove.mutateAsync(deleteTarget.id);
        }}
        successMessage="Lead deleted"
      />
    </div>
  );
}
