'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';
import { ChevronDown, Filter, KanbanSquare, Table2 } from 'lucide-react';
import type { PaginationState, SortingState } from '@tanstack/react-table';
import type { ProjectListParams } from '../../_shared/types/project.types';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Label } from '@/components/ui/label';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import {
  idFilterLabels,
  joinMulti,
  multiChipLabel,
  splitMulti,
} from '@/lib/list-filters/multiValue';
import { useListStateFromUrl } from '@/hooks/useListStateFromUrl';
import { useResetPageOnFilterChange } from '@/hooks/useResetPageOnFilterChange';
import { buildDetailSearch } from '@/lib/listNavQuery';
import { Switch } from '@/components/ui/switch';
import { useHasAnyPermission, useHasPermission } from '@/hooks/usePermissions';
import { useProjectStatusGraph } from '@/app/(protected)/project-sales/_shared/hooks/useProjectStatusGraph';
import {
  useChangeProjectStatus,
  useProjectParties,
  useProjectTypes,
  useProjects,
} from '../../_shared/hooks/useProjects';
import { ProjectsGrid } from '../../_shared/components/ProjectsGrid';
import { EmptyState, PipelineBoard } from './PipelineBoard';
import { POIntakeUploadDialog } from '../../[projectId]/components/POIntakeUploadDialog';
import { DeliveryScheduleUploadDialog } from '../../[projectId]/components/DeliveryScheduleUploadDialog';
import { PageHeader } from '@/components/common/PageHeader';
import { isSearchInFlight, useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { ListLoadFailure } from '@/components/common/ListLoadFailure';

type StartAction = 'upload-po' | 'upload-schedule' | null;

const VIEW_STORAGE_KEY = 'project-sales.pipeline.view';

type PipelineView = 'board' | 'grid';

/**
 * Pipeline: Board and Grid over one dataset, one toggle (AC-G2).
 *
 * The choice is remembered per browser because it tracks the person's job rather than
 * the data: a salesperson works the board, a manager reads the grid, and re-picking
 * on every visit is friction with no upside.
 *
 * The board pulls a bigger page than the grid on purpose. A board that paginates is a
 * board that lies about its column counts, and the whole point of the view is seeing
 * the shape of the funnel at a glance.
 */
export function PipelineClient() {
  const router = useRouter();
  const canEdit = useHasPermission('projects.projects.edit');
  const canRegister = useHasAnyPermission(['projects.projects.edit', 'projects.registrations.submit']);
  const [view, setView] = React.useState<PipelineView>('board');
  const [startAction, setStartAction] = React.useState<StartAction>(null);
  const {
    value: search,
    setValue: setSearch,
    debouncedValue: debouncedSearch,
    isSettling: debouncedSearchSettling,
    reset: resetSearch,
  } = useDebouncedSearch();
  const [ownerFilter, setOwnerFilter] = React.useState('');
  const [developerFilter, setDeveloperFilter] = React.useState('');
  const [typeFilter, setTypeFilter] = React.useState('');
  const [onlyCritical, setOnlyCritical] = React.useState(false);
  // A portal registration waiting for a decision, or refused (R6): '' is every project.
  const [approvalFilter, setApprovalFilter] = React.useState('');
  const [pagination, setPagination] = React.useState<PaginationState>({
    pageIndex: 0,
    pageSize: 50,
  });
  const [sorting, setSorting] = React.useState<SortingState>([
    { id: 'created_at', desc: true },
  ]);

  // Back hands the grid its own query string back, and the pager keeps rewriting
  // it, so the list reads it (S3-01). Below the state it writes: the hook applies
  // during the render, and a const read above its own line throws.
  useListStateFromUrl((urlState) => {
    setPagination({ pageIndex: urlState.pageIndex, pageSize: urlState.pageSize });
    setSorting(urlState.sorting);
    resetSearch(urlState.searchQuery);
    setDeveloperFilter(urlState.filters.developer_party_id ?? '');
    setOwnerFilter(urlState.filters.owner_user_id ?? '');
    setTypeFilter(urlState.filters.type_id ?? '');
    setOnlyCritical(urlState.filters.only_critical === 'true');
    setApprovalFilter(urlState.filters.approval_state ?? '');
  });

  React.useEffect(() => {
    const stored = window.localStorage.getItem(VIEW_STORAGE_KEY);
    if (stored === 'board' || stored === 'grid') setView(stored);
  }, []);

  // Narrowing the set changes which rows exist, so page 3 of the old set is a page of
  // nothing in the new one. Now that the filters live in the grid toolbar, landing on a
  // blank page would read as "the filter found nothing". Only on a CHANGE - the mount run
  // used to stamp page 1 over the page `useListStateFromUrl` had just restored.
  useResetPageOnFilterChange(setPagination, [
    debouncedSearch,
    developerFilter,
    typeFilter,
    onlyCritical,
    approvalFilter,
  ]);

  const graph = useProjectStatusGraph('project');
  const developers = useProjectParties({ party_type: 'developer', limit: 200 });
  const types = useProjectTypes();
  const move = useChangeProjectStatus();

  const listParams = React.useMemo(
    () => ({
      query: debouncedSearch || undefined,
      developer_party_id: developerFilter ? splitMulti(developerFilter) : undefined,
      owner_user_id: ownerFilter ? [ownerFilter] : undefined,
      type_id: typeFilter ? splitMulti(typeFilter) : undefined,
      only_critical: onlyCritical || undefined,
      approval_state: (approvalFilter || undefined) as ProjectListParams['approval_state'],
      page: view === 'board' ? 1 : pagination.pageIndex + 1,
      limit: view === 'board' ? 200 : pagination.pageSize,
      sort: sorting[0]?.id ?? 'created_at',
      dir: (sorting[0]?.desc ?? true ? 'desc' : 'asc') as 'asc' | 'desc',
    }),
    [
      debouncedSearch,
      developerFilter,
      ownerFilter,
      typeFilter,
      onlyCritical,
      approvalFilter,
      view,
      pagination,
      sorting,
    ],
  );

  const projects = useProjects(listParams);

  /**
   * Carried into the record URL so the project page's pager walks the SAME
   * searched, sorted, filtered page the reader was on. Grid view only: a board
   * card is not a list row, and the board holds 200 projects in one column-less
   * page that nothing pages through.
   */
  const detailSearch = React.useMemo(
    () =>
      buildDetailSearch(
        {
          pageIndex: pagination.pageIndex,
          pageSize: pagination.pageSize,
          sorting,
          searchQuery: debouncedSearch,
        },
        {
          developer_party_id: developerFilter,
          owner_user_id: ownerFilter,
          type_id: typeFilter,
          only_critical: onlyCritical ? 'true' : '',
          approval_state: approvalFilter,
        },
      ),
    [
      approvalFilter,
      debouncedSearch,
      developerFilter,
      onlyCritical,
      ownerFilter,
      pagination,
      sorting,
      typeFilter,
    ],
  );

  const statuses = React.useMemo(
    () =>
      (graph.data?.statuses ?? [])
        .filter((status) => status.is_active)
        .sort((a, b) => a.sort_order - b.sort_order),
    [graph.data],
  );

  const hasFilters = Boolean(
    debouncedSearch || developerFilter || ownerFilter || typeFilter || onlyCritical || approvalFilter,
  );
  const total = projects.data?.pagination.total ?? 0;
  const rows = projects.data?.data ?? [];

  function switchView(next: PipelineView) {
    setView(next);
    window.localStorage.setItem(VIEW_STORAGE_KEY, next);
  }

  const searchSlot = (
    <ListSearchInput
      value={search}
      onChange={setSearch}
      isSettling={isSearchInFlight(debouncedSearchSettling, projects.isFetching, debouncedSearch)}
      placeholder="Search title or code…"
      aria-label="Search projects"
      className="w-full"
    />
  );

  const activeFilterCount =
    (developerFilter ? 1 : 0) +
    (typeFilter ? 1 : 0) +
    (onlyCritical ? 1 : 0) +
    (approvalFilter ? 1 : 0);

  function clearFilters() {
    setSearch('');
    setDeveloperFilter('');
    setOwnerFilter('');
    setTypeFilter('');
    setOnlyCritical(false);
    setApprovalFilter('');
  }

  // One definition of "the pipeline filters", fed to the grid toolbar in Grid view and
  // to the board's own Filters button in Board view. Two copies would be two places for
  // a filter to be added and one place for it to be forgotten.
  const filterContent = (
    <div className="space-y-3">
      <div className="space-y-1.5">
        <Label htmlFor="filter-developer" className="text-xs text-muted-foreground">
          Developer
        </Label>
        <SearchableMultiSelect
          id="filter-developer"
          value={splitMulti(developerFilter)}
          onChange={(value) => setDeveloperFilter(joinMulti(value))}
          clearable
          renderTriggerLabel={(chosen) =>
            chosen.length ? (
              <span className="block truncate">{multiChipLabel('Developer', idFilterLabels(chosen))}</span>
            ) : (
              <span className="text-muted-foreground">All developers</span>
            )
          }
          options={(developers.data?.data ?? []).map((party) => ({
            value: party.id,
            label: party.name,
          }))}
          placeholder="All developers"
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="filter-type" className="text-xs text-muted-foreground">
          Type
        </Label>
        <SearchableMultiSelect
          id="filter-type"
          value={splitMulti(typeFilter)}
          onChange={(value) => setTypeFilter(joinMulti(value))}
          clearable
          renderTriggerLabel={(chosen) =>
            chosen.length ? (
              <span className="block truncate">{multiChipLabel('Type', idFilterLabels(chosen))}</span>
            ) : (
              <span className="text-muted-foreground">All types</span>
            )
          }
          options={(types.data ?? []).map((type) => ({
            value: type.id,
            label: type.name,
          }))}
          placeholder="All types"
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="filter-approval" className="text-xs text-muted-foreground">
          Approval
        </Label>
        <SearchableMultiSelect
          id="filter-approval"
          value={splitMulti(approvalFilter)}
          onChange={(value) => setApprovalFilter(joinMulti(value))}
          clearable
          options={[
            { value: 'pending', label: 'Awaiting approval' },
            { value: 'resubmitted', label: 'Resubmitted' },
            { value: 'rejected', label: 'Rejected' },
          ]}
          placeholder="Any approval state"
        />
      </div>
      <div className="flex items-center gap-2">
        <Switch
          id="filter-critical"
          checked={onlyCritical}
          onCheckedChange={setOnlyCritical}
        />
        <Label htmlFor="filter-critical" className="text-xs">
          Critical only
        </Label>
      </div>
      {hasFilters && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="w-full"
          onClick={clearFilters}
        >
          Clear filters
        </Button>
      )}
    </div>
  );

  return (
    <div className="space-y-5">
      <PageHeader
        title="Projects"
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <div
              className="inline-flex rounded-md border border-border p-0.5"
              role="group"
              aria-label="Projects view"
            >
              <Button
                type="button"
                size="sm"
                variant={view === 'board' ? 'primary' : 'ghost'}
                onClick={() => switchView('board')}
                aria-pressed={view === 'board'}
                aria-label="Board view"
                title="Board view"
                mode="icon"
              >
                <KanbanSquare className="size-4" aria-hidden />
              </Button>
              <Button
                type="button"
                size="sm"
                variant={view === 'grid' ? 'primary' : 'ghost'}
                onClick={() => switchView('grid')}
                aria-pressed={view === 'grid'}
                aria-label="Grid view"
                title="Grid view"
                mode="icon"
              >
                <Table2 className="size-4" aria-hidden />
              </Button>
            </div>
            {canRegister && (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button type="button">
                    Start
                    <ChevronDown className="size-4" aria-hidden />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onSelect={() => router.push('/project-sales/new')}>
                    Register a project
                  </DropdownMenuItem>
                  {canEdit && (
                    <>
                      <DropdownMenuItem onSelect={() => setStartAction('upload-po')}>
                        Upload PO
                      </DropdownMenuItem>
                      <DropdownMenuItem onSelect={() => setStartAction('upload-schedule')}>
                        Upload delivery schedule
                      </DropdownMenuItem>
                    </>
                  )}
                </DropdownMenuContent>
              </DropdownMenu>
            )}
          </div>
        }
      />

      {/* Board has no grid toolbar to host them, so it carries the same two controls in
          the same order the toolbar uses. Grid view feeds them into the toolbar instead,
          so the filters never sit in a second card above the table. */}
      {view === 'board' && (
        <div className="flex flex-wrap items-center gap-2">
          {searchSlot}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm" className="gap-1.5">
                <Filter className="size-4" aria-hidden />
                Filters
                {activeFilterCount > 0 && (
                  <Badge variant="secondary" className="ms-0.5 px-1 py-0 text-[10px]">
                    {activeFilterCount}
                  </Badge>
                )}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-72 p-3">
              {filterContent}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      )}

      {view === 'board' && !projects.isLoading && projects.error && total === 0 ? (
        // A failed read is not "no projects registered yet" (lever L2).
        <div className="rounded-lg border px-4 py-6 text-sm">
          <ListLoadFailure error={projects.error} onRetry={() => void projects.refetch()} />
        </div>
      ) : view === 'board' && !projects.isLoading && total === 0 ? (
        hasFilters ? (
          <EmptyState
            title="No projects match these filters"
            body="Clear the filters to see every project."
          />
        ) : (
          <EmptyState
            title="No projects registered yet"
            body="Register one from Start."
          />
        )
      ) : view === 'board' ? (
        <PipelineBoard
          statuses={statuses}
          projects={rows}
          isLoading={projects.isLoading || graph.isLoading}
          movingProjectId={move.isPending ? move.variables?.projectId : null}
          onMove={(projectId, toStatusId) => {
            const project = rows.find((row) => row.id === projectId);
            if (!project || project.status_id === toStatusId) return;
            move.mutate({ projectId, toStatusId });
          }}
        />
      ) : (
        <ProjectsGrid
          projects={rows}
          total={total}
          isLoading={projects.isLoading}
          error={projects.error}
          isFetching={projects.isFetching}
          isPlaceholderData={projects.isPlaceholderData}
          pagination={pagination}
          onPaginationChange={setPagination}
          sorting={sorting}
          onSortingChange={setSorting}
          onRefresh={() => void projects.refetch()}
          searchSlot={searchSlot}
          filters={{
            kind: 'custom',
            active: activeFilterCount > 0,
            activeCount: activeFilterCount,
            content: filterContent,
          }}
          // Its own key, separate from the Projects list: the same table serves two
          // jobs here, and a manager reading the pipeline arranges it differently
          // from somebody working the flat list.
          rowHref={(project) =>
            `/project-sales/${project.id}${detailSearch ? `?${detailSearch}` : ''}`
          }
          listingKey="projects.projects.view::pipeline"
          emptyMessage={
            <div className="px-6 py-10 text-center">
              <p className="text-sm font-semibold">
                {hasFilters
                  ? 'No projects match these filters'
                  : 'No projects registered yet'}
              </p>
              <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                {hasFilters
                  ? 'Clear the filters to see every project.'
                  : 'Register one from Start.'}
              </p>
            </div>
          }
        />
      )}

      {startAction === 'upload-po' && (
        <POIntakeUploadDialog
          onDone={() => setStartAction(null)}
          pipelineListQuery={detailSearch}
        />
      )}
      {startAction === 'upload-schedule' && (
        <DeliveryScheduleUploadDialog
          onDone={() => setStartAction(null)}
          pipelineListQuery={detailSearch}
        />
      )}
    </div>
  );
}
