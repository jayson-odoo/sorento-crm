'use client';

import * as React from 'react';
import { KanbanSquare, Plus, Search, Table2, X } from 'lucide-react';
import type { PaginationState, SortingState } from '@tanstack/react-table';
import { Button } from '@/components/ui/button';
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
import { EmptyState, PipelineBoard } from './PipelineBoard';
import { PipelineGrid } from './PipelineGrid';
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
            >
              <KanbanSquare className="size-4" aria-hidden />
              Board
            </Button>
            <Button
              type="button"
              size="sm"
              variant={view === 'grid' ? 'primary' : 'ghost'}
              onClick={() => switchView('grid')}
              aria-pressed={view === 'grid'}
            >
              <Table2 className="size-4" aria-hidden />
              Grid
            </Button>
          </div>
          <Button type="button" onClick={() => setRegisterOpen(true)}>
            <Plus className="size-4" aria-hidden />
            Register project
          </Button>
        </div>
      </header>

      <section className="grid gap-3 rounded-lg border border-border bg-muted/30 p-3 sm:grid-cols-2 lg:grid-cols-4">
        {view === 'board' && <div className="sm:col-span-2 lg:col-span-1">{searchSlot}</div>}
        <div className="space-y-1.5">
          <Label htmlFor="filter-developer" className="text-xs">
            Developer
          </Label>
          <SearchableSelect
            id="filter-developer"
            value={developerFilter}
            onChange={setDeveloperFilter}
            clearable
            size="sm"
            options={(developers.data?.data ?? []).map((party) => ({
              value: party.id,
              label: party.name,
            }))}
            placeholder="All developers"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="filter-type" className="text-xs">
            Type
          </Label>
          <SearchableSelect
            id="filter-type"
            value={typeFilter}
            onChange={setTypeFilter}
            clearable
            size="sm"
            options={(types.data ?? []).map((type) => ({
              value: type.id,
              label: type.name,
            }))}
            placeholder="All types"
          />
        </div>
        <div className="flex items-end gap-4">
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
              size="sm"
              variant="ghost"
              onClick={() => {
                setSearch('');
                setDeveloperFilter('');
                setOwnerFilter('');
                setTypeFilter('');
                setOnlyCritical(false);
              }}
            >
              Clear
            </Button>
          )}
        </div>
      </section>

      {!projects.isLoading && total === 0 ? (
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
        <PipelineGrid
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
        />
      )}

      <RegisterProjectDialog open={registerOpen} onOpenChange={setRegisterOpen} />
    </div>
  );
}
