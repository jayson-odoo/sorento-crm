'use client';

import * as React from 'react';
import { Filter, KanbanSquare, Plus, Search, Table2, X } from 'lucide-react';
import type { PaginationState, SortingState } from '@tanstack/react-table';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { Switch } from '@/components/ui/switch';
import { useStatusGraph } from '@/app/(protected)/system-management/status-graphs/hooks/useStatusGraphs';
import {
  useChangeProjectStatus,
  useProjectParties,
  useProjectTypes,
  useProjects,
} from '../../_shared/hooks/useProjects';
import { ProjectsGrid } from '../../_shared/components/ProjectsGrid';
import { EmptyState, PipelineBoard } from './PipelineBoard';
import { RegisterProjectDialog } from './RegisterProjectDialog';

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
  const [view, setView] = React.useState<PipelineView>('board');
  const [registerOpen, setRegisterOpen] = React.useState(false);
  const [search, setSearch] = React.useState('');
  const [debouncedSearch, setDebouncedSearch] = React.useState('');
  const [ownerFilter, setOwnerFilter] = React.useState('');
  const [developerFilter, setDeveloperFilter] = React.useState('');
  const [typeFilter, setTypeFilter] = React.useState('');
  const [onlyCritical, setOnlyCritical] = React.useState(false);
  const [pagination, setPagination] = React.useState<PaginationState>({
    pageIndex: 0,
    pageSize: 50,
  });
  const [sorting, setSorting] = React.useState<SortingState>([
    { id: 'created_at', desc: true },
  ]);

  React.useEffect(() => {
    const stored = window.localStorage.getItem(VIEW_STORAGE_KEY);
    if (stored === 'board' || stored === 'grid') setView(stored);
  }, []);

  React.useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearch(search.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [search]);

  // Narrowing the set changes which rows exist, so page 3 of the old set is a page of
  // nothing in the new one. Now that the filters live in the grid toolbar, landing on a
  // blank page would read as "the filter found nothing".
  React.useEffect(() => {
    setPagination((previous) => ({ ...previous, pageIndex: 0 }));
  }, [debouncedSearch, developerFilter, typeFilter, onlyCritical]);

  const graph = useStatusGraph('project', null, false);
  const developers = useProjectParties({ party_type: 'developer', limit: 200 });
  const types = useProjectTypes();
  const move = useChangeProjectStatus();

  const listParams = React.useMemo(
    () => ({
      query: debouncedSearch || undefined,
      developer_party_id: developerFilter ? [developerFilter] : undefined,
      owner_user_id: ownerFilter ? [ownerFilter] : undefined,
      type_id: typeFilter ? [typeFilter] : undefined,
      only_critical: onlyCritical || undefined,
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
      view,
      pagination,
      sorting,
    ],
  );

  const projects = useProjects(listParams);

  const statuses = React.useMemo(
    () =>
      (graph.data?.statuses ?? [])
        .filter((status) => status.is_active)
        .sort((a, b) => a.sort_order - b.sort_order),
    [graph.data],
  );

  const hasFilters = Boolean(
    debouncedSearch || developerFilter || ownerFilter || typeFilter || onlyCritical,
  );
  const total = projects.data?.pagination.total ?? 0;
  const rows = projects.data?.data ?? [];

  function switchView(next: PipelineView) {
    setView(next);
    window.localStorage.setItem(VIEW_STORAGE_KEY, next);
  }

  const searchSlot = (
    <div className="relative">
      <Search
        className="absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
        aria-hidden
      />
      <Input
        placeholder="Search title or code…"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
        className="w-full ps-9 sm:w-64"
        aria-label="Search projects"
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

  const activeFilterCount =
    (developerFilter ? 1 : 0) + (typeFilter ? 1 : 0) + (onlyCritical ? 1 : 0);

  function clearFilters() {
    setSearch('');
    setDeveloperFilter('');
    setOwnerFilter('');
    setTypeFilter('');
    setOnlyCritical(false);
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
        <SearchableSelect
          id="filter-developer"
          value={developerFilter}
          onChange={setDeveloperFilter}
          clearable
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
        <SearchableSelect
          id="filter-type"
          value={typeFilter}
          onChange={setTypeFilter}
          clearable
          options={(types.data ?? []).map((type) => ({
            value: type.id,
            label: type.name,
          }))}
          placeholder="All types"
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
      <header className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold">Pipeline</h1>
          <p className="text-sm text-muted-foreground">
            Every project in the company, so nobody works a development twice.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div
            className="inline-flex rounded-md border border-border p-0.5"
            role="group"
            aria-label="Pipeline view"
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
          <Button type="button" onClick={() => setRegisterOpen(true)}>
            <Plus className="size-4" aria-hidden />
            Register project
          </Button>
        </div>
      </header>

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

      {view === 'board' && !projects.isLoading && total === 0 ? (
        hasFilters ? (
          <EmptyState
            title="No projects match these filters"
            body="Widen or clear the filters to see the rest of the pipeline."
          />
        ) : (
          <EmptyState
            title="No projects registered yet"
            body="Register the development you are pursuing. Claiming it early is what stops two people quoting the same tender."
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
          isFetching={projects.isFetching}
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
                  ? 'Widen or clear the filters to see the rest of the pipeline.'
                  : 'Register the development you are pursuing. Claiming it early is what stops two people quoting the same tender.'}
              </p>
            </div>
          }
        />
      )}

      <RegisterProjectDialog open={registerOpen} onOpenChange={setRegisterOpen} />
    </div>
  );
}
