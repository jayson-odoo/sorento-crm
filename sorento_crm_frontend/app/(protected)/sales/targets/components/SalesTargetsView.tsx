'use client';

import { useMemo, useState, type ReactNode } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import {
  ColumnDef,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { Plus, UserRound, UsersRound } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { DatePicker } from '@/components/ui/date-picker';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Container } from '@/components/common/container';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { PageHeader } from '@/components/common/PageHeader';
import { PillOverflow } from '@/components/common/PillOverflow';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import {
  isSearchInFlight,
  useDebouncedSearch,
} from '@/hooks/useDebouncedSearch';
import { useHasPermission } from '@/hooks/usePermissions';
import {
  formatLocalDateToYyyyMmDd,
  todayMalaysiaYyyyMmDd,
} from '@/lib/helpers';
import { useSalesTargets } from '../hooks/useSalesTargets';
import { foldBySubject, type FoldedRow } from '../lib/fold';
import {
  BASIS_LABEL,
  dateFromYmd,
  METRIC_LABEL,
  formatFigure,
  formatPct,
  scopeSummary,
} from '../lib/format';
import type {
  SalesTargetRow,
  TargetSubjectKind,
} from '../types/salesTarget.types';
import SetTargetModal from './SetTargetModal';

type Keyed = SalesTargetRow & { subject_key: string; end_date: string | null };
type Line = FoldedRow<Keyed>;

interface ModalState {
  kind: TargetSubjectKind;
  subjectId?: string;
}

const TABS: {
  value: TargetSubjectKind;
  label: string;
  icon: typeof UsersRound;
}[] = [
  { value: 'team', label: 'Teams', icon: UsersRound },
  { value: 'agent', label: 'Agents', icon: UserRound },
];

/** Keep the tab, date and team filter in the URL without a navigation (a shareable view). */
function writeUrl(next: Record<string, string>) {
  if (typeof window === 'undefined') return;
  const params = new URLSearchParams(window.location.search);
  for (const [key, value] of Object.entries(next)) {
    if (value) params.set(key, value);
    else params.delete(key);
  }
  const search = params.toString();
  window.history.replaceState(
    window.history.state,
    '',
    `${window.location.pathname}${search ? `?${search}` : ''}`,
  );
}

function subjectId(row: SalesTargetRow): string {
  return (
    (row.subject_kind === 'team' ? row.sales_team_id : row.sales_agent_id) ?? ''
  );
}

/** Every target of a line, one per target (a split target has one period on the date). */
function targetsOf(line: Line): Keyed[] {
  return line.targets.filter((t) => t.target_id);
}

function MeasuresCell({ row }: { row: SalesTargetRow }) {
  if (!row.metric) return <span className="text-muted-foreground">-</span>;
  const items = [
    { key: 'metric', label: METRIC_LABEL[row.metric] },
    { key: 'basis', label: row.basis ? BASIS_LABEL[row.basis] : '' },
    {
      key: 'scope',
      label: scopeSummary(row.product_scope, row.scope_labels.length),
    },
  ].filter((i) => i.label);
  return (
    <PillOverflow
      ariaLabel={`What ${row.name ?? 'the target'} counts`}
      items={items}
      renderPopover={(all) => (
        <ul className="flex flex-col gap-1 text-sm">
          {all.map((i) => (
            <li key={i.key}>{i.label}</li>
          ))}
          {row.scope_labels.map((label) => (
            <li
              key={label}
              className="truncate text-muted-foreground"
              title={label}
            >
              {label}
            </li>
          ))}
        </ul>
      )}
    />
  );
}

/**
 * Sales > Targets (UAC S1-14, S1-15, S1-18, S1-21, S1-22, S6-7, S6-10; plan 3.9).
 *
 * Opens on the **Teams** tab (N5): one line per active team, then a "No team" line (active
 * agents in no team, opening the Agents tab filtered to them) and the "Unassigned" line
 * (orders with no agent in the month). **Agents** is flat, one line per agent, with a
 * clearable Team filter that includes "No team". The API returns one row per target period
 * active on the date; `foldBySubject` makes it one line per subject (N3, N4): the numbers are
 * the first target's, the Targets cell names them all. Set target sits alone in the header
 * (L3) and presets the open tab's kind. The date, tab and team filter live in the URL.
 */
export default function SalesTargetsView() {
  const params = useSearchParams();
  const canAdd = useHasPermission('sales.targets.add');
  const [tab, setTab] = useState<TargetSubjectKind>(
    params.get('tab') === 'agent' ? 'agent' : 'team',
  );
  const [on, setOn] = useState(params.get('on') || todayMalaysiaYyyyMmDd());
  const [teamFilter, setTeamFilter] = useState(params.get('team') ?? '');
  const [modal, setModal] = useState<ModalState | null>(null);
  const {
    value: searchQuery,
    setValue: setSearchQuery,
    debouncedValue: debouncedSearch,
    isSettling,
  } = useDebouncedSearch();

  const listParams = {
    on,
    subject: tab,
    ...(tab === 'agent' && teamFilter ? { salesTeamId: teamFilter } : {}),
    ...(debouncedSearch ? { query: debouncedSearch } : {}),
  };
  const { data, isLoading, isFetching, isError, error } =
    useSalesTargets(listParams);
  // The Team filter's choices: the teams on the landing's own list (usually already cached).
  const { data: teamList } = useSalesTargets(
    { on, subject: 'team' },
    tab === 'agent',
  );

  const lines = useMemo<Line[]>(
    () =>
      foldBySubject(
        (data?.rows ?? []).map((row) => ({
          ...row,
          subject_key: subjectId(row),
          end_date: row.end_date ?? null,
        })),
      ),
    [data],
  );
  const teamOptions = useMemo(() => {
    const seen = new Map<string, string>();
    for (const row of teamList?.rows ?? []) {
      if (row.sales_team_id && !seen.has(row.sales_team_id))
        seen.set(row.sales_team_id, row.subject_label);
    }
    return [
      { value: 'none', label: 'No team' },
      ...Array.from(seen, ([value, label]) => ({ value, label })).sort((a, b) =>
        a.label.localeCompare(b.label),
      ),
    ];
  }, [teamList]);

  const changeTab = (value: string) => {
    const next: TargetSubjectKind = value === 'agent' ? 'agent' : 'team';
    setTab(next);
    writeUrl({
      tab: next === 'agent' ? 'agent' : '',
      team: next === 'agent' ? teamFilter : '',
    });
  };
  const changeOn = (value: string) => {
    if (!value) return;
    setOn(value);
    writeUrl({ on: value });
  };
  const changeTeam = (value: string) => {
    setTeamFilter(value);
    writeUrl({ team: value });
  };
  const showNoTeam = () => {
    setTab('agent');
    setTeamFilter('none');
    writeUrl({ tab: 'agent', team: 'none' });
  };

  const headerAction = canAdd ? (
    <Button variant="primary" onClick={() => setModal({ kind: tab })}>
      <Plus className="size-4" />
      Set target
    </Button>
  ) : undefined;

  const emptyMessage = debouncedSearch
    ? 'Nothing matches this search.'
    : tab === 'team'
      ? 'No active sales teams'
      : 'No sales agents here';

  return (
    <>
      <Container>
        <PageHeader title="Targets" actions={headerAction} />
      </Container>
      <Container>
        <div className="space-y-3">
          <Tabs value={tab} onValueChange={changeTab}>
            <TabsList>
              {TABS.map((t) => (
                <TabsTrigger
                  key={t.value}
                  value={t.value}
                  onClick={() => changeTab(t.value)}
                >
                  <t.icon className="size-4" />
                  {t.label}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
          {isError ? (
            <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
              {error instanceof Error
                ? error.message
                : 'Failed to load targets.'}
            </div>
          ) : null}
          {/* One grid per tab (keyed): the two tabs have different columns, and a shared table
              instance carried the Teams tab's column order into the Agents tab's saved layout. */}
          <TargetsGrid
            key={tab}
            tab={tab}
            lines={lines}
            on={on}
            canAdd={canAdd}
            isLoading={isLoading}
            emptyMessage={emptyMessage}
            onSetTarget={setModal}
            toolbar={
              <CardHeader className="flex flex-wrap items-end gap-3 py-3">
                <div className="flex flex-col gap-1">
                  <Label
                    htmlFor="targets-active-on"
                    className="text-xs text-muted-foreground"
                  >
                    Active on
                  </Label>
                  <DatePicker
                    id="targets-active-on"
                    value={dateFromYmd(on)}
                    onChange={(d) =>
                      d && changeOn(formatLocalDateToYyyyMmDd(d))
                    }
                    required
                    className="w-52"
                  />
                </div>
                <ListSearchInput
                  value={searchQuery}
                  onChange={setSearchQuery}
                  isSettling={isSearchInFlight(
                    isSettling,
                    isFetching,
                    debouncedSearch,
                  )}
                  placeholder={
                    tab === 'team'
                      ? 'Search teams or targets...'
                      : 'Search agents or targets...'
                  }
                  className="w-full sm:w-64"
                />
                {tab === 'agent' ? (
                  <div className="flex flex-col gap-1">
                    <Label
                      htmlFor="targets-team-filter"
                      className="text-xs text-muted-foreground"
                    >
                      Team
                    </Label>
                    <SearchableSelect
                      id="targets-team-filter"
                      value={teamFilter}
                      onChange={changeTeam}
                      options={teamOptions}
                      placeholder="All teams"
                      clearable
                      className="w-full sm:w-56"
                    />
                  </div>
                ) : null}
              </CardHeader>
            }
            footer={
              <>
                {tab === 'team' && data ? (
                  <div className="flex flex-col divide-y border-t text-sm">
                    <button
                      type="button"
                      onClick={showNoTeam}
                      className="flex min-w-0 items-center justify-between gap-3 px-4 py-2.5 text-start hover:bg-muted/40"
                    >
                      <span className="font-medium">No team</span>
                      <span className="truncate text-muted-foreground">
                        {`${data.no_team_count} agent${data.no_team_count === 1 ? '' : 's'}`}
                      </span>
                    </button>
                    <div className="flex min-w-0 items-center justify-between gap-3 px-4 py-2.5">
                      <span className="font-medium">Unassigned</span>
                      <span className="truncate tabular-nums text-muted-foreground">
                        {`RM ${formatFigure(data.unassigned_amount)}`}
                      </span>
                    </div>
                  </div>
                ) : null}
              </>
            }
          />
        </div>
      </Container>
      {modal ? (
        <SetTargetModal
          open
          onOpenChange={(open) => (open ? null : setModal(null))}
          presetKind={modal.kind}
          presetSubjectId={modal.subjectId}
        />
      ) : null}
    </>
  );
}

/**
 * The Targets grid for one tab, one line per subject (S1-21). Its own component so each tab
 * gets its own table state (column order, sizes), saved under its own listing key.
 */
function TargetsGrid({
  tab,
  lines,
  on,
  canAdd,
  isLoading,
  emptyMessage,
  onSetTarget,
  toolbar,
  footer,
}: {
  tab: TargetSubjectKind;
  lines: Line[];
  on: string;
  canAdd: boolean;
  isLoading: boolean;
  emptyMessage: string;
  onSetTarget: (modal: ModalState) => void;
  toolbar: ReactNode;
  footer: ReactNode;
}) {
  const columns = useMemo<ColumnDef<Line>[]>(() => {
    const subjectColumn: ColumnDef<Line> = {
      id: 'subject',
      header: ({ column }) => (
        <DataGridColumnHeader
          title={tab === 'team' ? 'Team' : 'Agent'}
          column={column}
        />
      ),
      cell: ({ row }) => {
        const { primary } = row.original;
        return (
          <span className="flex min-w-0 items-center gap-2">
            <span
              className={
                primary.left_on
                  ? 'truncate text-muted-foreground'
                  : 'truncate font-medium'
              }
              title={primary.subject_label}
            >
              {primary.subject_label}
            </span>
          </span>
        );
      },
      size: tab === 'team' ? 150 : 200,
      meta: {
        headerTitle: tab === 'team' ? 'Team' : 'Agent',
        skeleton: <Skeleton className="h-4 w-28" />,
      },
    };
    const secondColumn: ColumnDef<Line> =
      tab === 'team'
        ? {
            id: 'agents',
            header: ({ column }) => (
              <DataGridColumnHeader title="Agents" column={column} />
            ),
            cell: ({ row }) => {
              const members = row.original.primary.members ?? [];
              return members.length ? (
                <PillOverflow
                  ariaLabel={`Agents in ${row.original.primary.subject_label}`}
                  items={members.map((m) => ({
                    key: m.sales_agent_id,
                    label: m.label,
                  }))}
                  renderPopover={(items) => (
                    <ul className="flex flex-col gap-1 text-sm">
                      {items.map((i) => (
                        <li key={i.key}>{i.label}</li>
                      ))}
                    </ul>
                  )}
                />
              ) : (
                <span className="text-muted-foreground">No agents</span>
              );
            },
            size: 170,
            enableSorting: false,
            meta: {
              headerTitle: 'Agents',
              skeleton: <Skeleton className="h-5 w-32" />,
            },
          }
        : {
            id: 'team',
            header: ({ column }) => (
              <DataGridColumnHeader title="Team" column={column} />
            ),
            cell: ({ row }) => {
              const name = row.original.primary.team_name;
              return name ? (
                <span className="block truncate" title={name}>
                  {name}
                </span>
              ) : (
                <span className="text-muted-foreground">No team</span>
              );
            },
            size: 120,
            enableSorting: false,
            meta: {
              headerTitle: 'Team',
              skeleton: <Skeleton className="h-4 w-20" />,
            },
          };

    return [
      subjectColumn,
      secondColumn,
      {
        id: 'targets',
        header: ({ column }) => (
          <DataGridColumnHeader title="Targets" column={column} />
        ),
        cell: ({ row }) => {
          const line = row.original;
          const targets = targetsOf(line);
          if (targets.length === 0) {
            return (
              <span className="flex min-w-0 items-center gap-2">
                <span className="text-muted-foreground">No target</span>
                {canAdd ? (
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-7"
                    onClick={(event) => {
                      event.stopPropagation();
                      onSetTarget({
                        kind: line.primary.subject_kind,
                        subjectId: line.subject_key,
                      });
                    }}
                  >
                    Set target
                  </Button>
                ) : null}
              </span>
            );
          }
          if (targets.length === 1) {
            return (
              <Link
                href={`/sales/targets/${targets[0].target_id}`}
                onClick={(event) => event.stopPropagation()}
                className="block truncate text-primary hover:underline"
                title={targets[0].name ?? undefined}
              >
                {targets[0].name}
              </Link>
            );
          }
          return (
            <PillOverflow
              ariaLabel={`Targets of ${line.primary.subject_label}`}
              items={targets.map((t) => ({
                key: t.target_id as string,
                label: t.name ?? '',
              }))}
              renderPopover={() => (
                <ul className="flex flex-col gap-1 text-sm">
                  {targets.map((t) => (
                    <li
                      key={t.target_id}
                      className="flex min-w-0 items-center justify-between gap-3"
                    >
                      <Link
                        href={`/sales/targets/${t.target_id}`}
                        className="truncate text-primary hover:underline"
                        title={t.name ?? undefined}
                      >
                        {t.name}
                      </Link>
                      <span className="shrink-0 tabular-nums">
                        {formatPct(t.achieved_pct)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            />
          );
        },
        size: 160,
        enableSorting: false,
        meta: {
          headerTitle: 'Targets',
          skeleton: <Skeleton className="h-5 w-32" />,
        },
      },
      {
        id: 'measures',
        header: ({ column }) => (
          <DataGridColumnHeader title="Measures" column={column} />
        ),
        cell: ({ row }) => <MeasuresCell row={row.original.primary} />,
        size: 190,
        enableSorting: false,
        meta: {
          headerTitle: 'Measures',
          skeleton: <Skeleton className="h-5 w-24" />,
        },
      },
      {
        id: 'target',
        header: ({ column }) => (
          <DataGridColumnHeader title="Target" column={column} />
        ),
        cell: ({ row }) => (
          <span className="block truncate text-end tabular-nums">
            {formatFigure(row.original.primary.target_value)}
          </span>
        ),
        size: 100,
        enableSorting: false,
        meta: {
          headerTitle: 'Target',
          skeleton: <Skeleton className="h-4 w-16" />,
        },
      },
      {
        id: 'achieved',
        header: ({ column }) => (
          <DataGridColumnHeader title="Achieved" column={column} />
        ),
        cell: ({ row }) => (
          <span className="block truncate text-end tabular-nums">
            {formatFigure(row.original.primary.achieved_value)}
          </span>
        ),
        size: 100,
        enableSorting: false,
        meta: {
          headerTitle: 'Achieved',
          skeleton: <Skeleton className="h-4 w-16" />,
        },
      },
      {
        id: 'pct',
        header: ({ column }) => (
          <DataGridColumnHeader title="%" column={column} />
        ),
        cell: ({ row }) => {
          const pct = row.original.primary.achieved_pct;
          return (
            <span
              className={
                pct !== null && pct >= 100
                  ? 'block text-end font-medium tabular-nums text-success'
                  : 'block text-end tabular-nums'
              }
            >
              {formatPct(pct)}
            </span>
          );
        },
        size: 70,
        enableSorting: false,
        meta: { headerTitle: '%', skeleton: <Skeleton className="h-4 w-10" /> },
      },
    ];
  }, [tab, canAdd, onSetTarget]);

  const table = useReactTable({
    columns,
    data: lines,
    getRowId: (row) => row.subject_key,
    getCoreRowModel: getCoreRowModel(),
    // The server orders subjects by name, and the first target by the fold rule.
    enableSorting: false,
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  return (
    <DataGrid
      table={table}
      recordCount={lines.length}
      isLoading={isLoading}
      listingKey={`sales.targets.view::${tab}`}
      tableLayout={{ width: 'fixed', columnsResizable: true }}
      emptyMessage={emptyMessage}
      rowHref={(line) =>
        line.primary.subject_kind === 'team'
          ? `/sales/teams/${line.subject_key}?on=${on}`
          : targetsOf(line)[0]?.target_id
            ? `/sales/targets/${targetsOf(line)[0].target_id}`
            : ''
      }
    >
      <Card>
        {toolbar}
        <CardTable>
          <DataGridTable />
        </CardTable>
        {footer}
      </Card>
    </DataGrid>
  );
}
