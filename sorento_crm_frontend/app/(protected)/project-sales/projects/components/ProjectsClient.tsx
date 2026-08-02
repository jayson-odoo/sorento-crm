'use client';

import * as React from 'react';
import Link from 'next/link';
import type { PaginationState, SortingState } from '@tanstack/react-table';
import { KanbanSquare, Plus, Search, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { ProjectsGrid } from '../../_shared/components/ProjectsGrid';
import { useProjectParties, useProjectTypes, useProjects } from '../../_shared/hooks/useProjects';
import { RegisterProjectDialog } from '../../pipeline/components/RegisterProjectDialog';

/**
 * Projects: the flat list of everything registered.
 *
 * It exists because the pipeline is a board, and a board answers "where is everything
 * in the funnel" rather than "find me this project". Somebody who knows the name of the
 * job they want should not have to read a column of cards to reach it, and until this
 * page existed the only way into a project was through that board.
 *
 * Same records, same grid, same column preferences machinery as the pipeline's grid
 * view. Only the surrounding page differs: no board toggle, no stage columns, just the
 * list with search and the filters that narrow it.
 */
export function ProjectsClient() {
  const [registerOpen, setRegisterOpen] = React.useState(false);
  const [search, setSearch] = React.useState('');
  const [debouncedSearch, setDebouncedSearch] = React.useState('');
  const [developerFilter, setDeveloperFilter] = React.useState('');
  const [typeFilter, setTypeFilter] = React.useState('');
  const [onlyCritical, setOnlyCritical] = React.useState(false);
  const [pagination, setPagination] = React.useState<PaginationState>({
    pageIndex: 0,
    pageSize: 25,
  });
  const [sorting, setSorting] = React.useState<SortingState>([
    { id: 'created_at', desc: true },
  ]);

  React.useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearch(search.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [search]);

  // Narrowing the set changes which rows exist, so page 3 of the old set is a page of
  // nothing in the new one.
  React.useEffect(() => {
    setPagination((previous) => ({ ...previous, pageIndex: 0 }));
  }, [debouncedSearch, developerFilter, typeFilter, onlyCritical]);

  const developers = useProjectParties({ party_type: 'developer', limit: 200 });
  const types = useProjectTypes();

  const projects = useProjects({
    query: debouncedSearch || undefined,
    developer_party_id: developerFilter ? [developerFilter] : undefined,
    type_id: typeFilter ? [typeFilter] : undefined,
    only_critical: onlyCritical || undefined,
    page: pagination.pageIndex + 1,
    limit: pagination.pageSize,
    sort: sorting[0]?.id ?? 'created_at',
    dir: (sorting[0]?.desc ?? true) ? 'desc' : 'asc',
  });

  const rows = projects.data?.data ?? [];
  const total = projects.data?.pagination.total ?? 0;
  const activeFilterCount =
    (developerFilter ? 1 : 0) + (typeFilter ? 1 : 0) + (onlyCritical ? 1 : 0);
  const narrowed = activeFilterCount > 0 || Boolean(debouncedSearch);

  const searchSlot = (
    <div className="relative w-full max-w-xs">
      <Search
        className="pointer-events-none absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
        aria-hidden
      />
      <Input
        value={search}
        onChange={(event) => setSearch(event.target.value)}
        placeholder="Search title or code…"
        className="ps-9"
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
        <div className="min-w-0 break-words">
          <h1 className="text-xl font-semibold">Projects</h1>
          <p className="text-sm text-muted-foreground">
            Every development the company has registered, newest first.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button asChild variant="outline">
            <Link href="/project-sales/pipeline">
              <KanbanSquare className="size-4" aria-hidden />
              Pipeline board
            </Link>
          </Button>
          <Button type="button" onClick={() => setRegisterOpen(true)}>
            <Plus className="size-4" aria-hidden />
            Register project
          </Button>
        </div>
      </header>

      {projects.isError ? (
        <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-6 py-10 text-center">
          <h2 className="text-sm font-semibold text-destructive">
            Projects could not be loaded
          </h2>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
            {projects.error instanceof Error
              ? projects.error.message
              : 'Try again shortly.'}
          </p>
          <Button
            type="button"
            variant="outline"
            className="mt-4"
            onClick={() => void projects.refetch()}
          >
            Try again
          </Button>
        </div>
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
          listingKey="projects.projects.view::projects"
          filters={{
            kind: 'custom',
            active: activeFilterCount > 0,
            activeCount: activeFilterCount,
            content: (
              <div className="space-y-3">
                <div className="space-y-1.5">
                  <Label className="text-xs text-muted-foreground">Developer</Label>
                  <SearchableSelect
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
                  <Label className="text-xs text-muted-foreground">Type</Label>
                  <SearchableSelect
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
                    id="projects-filter-critical"
                    checked={onlyCritical}
                    onCheckedChange={setOnlyCritical}
                  />
                  <Label htmlFor="projects-filter-critical" className="text-xs">
                    Critical only
                  </Label>
                </div>
                {activeFilterCount > 0 && (
                  <Button
                    variant="outline"
                    size="sm"
                    className="w-full"
                    onClick={() => {
                      setDeveloperFilter('');
                      setTypeFilter('');
                      setOnlyCritical(false);
                    }}
                  >
                    Clear filters
                  </Button>
                )}
              </div>
            ),
          }}
          emptyMessage={
            <div className="px-6 py-10 text-center">
              <p className="text-sm font-semibold">
                {narrowed
                  ? 'No projects match these filters'
                  : 'No projects registered yet'}
              </p>
              <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                {narrowed
                  ? 'Widen or clear the filters to see the rest of the pipeline.'
                  : 'Register the development you are pursuing. Claiming it early is what stops two people quoting the same tender.'}
              </p>
              <Button
                type="button"
                className="mt-4"
                onClick={() => setRegisterOpen(true)}
              >
                <Plus className="size-4" aria-hidden />
                Register project
              </Button>
            </div>
          }
        />
      )}

      <RegisterProjectDialog open={registerOpen} onOpenChange={setRegisterOpen} />
    </div>
  );
}
