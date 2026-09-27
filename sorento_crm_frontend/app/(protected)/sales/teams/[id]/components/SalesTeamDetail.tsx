'use client';

import { useMemo, useState, type ReactNode } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Info, LoaderCircleIcon, Plus, SquarePen, Target, UsersRound, X } from 'lucide-react';
import { Badge, BadgeDot } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardHeader } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import DetailActions from '@/components/common/DetailActions';
import { PillOverflow } from '@/components/common/PillOverflow';
import RecordNavigation from '@/components/common/RecordNavigation';
import type { RecordAction } from '@/components/common/recordActions';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { useHasPermission } from '@/hooks/usePermissions';
import { formatDateInMalaysia, todayMalaysiaYyyyMmDd } from '@/lib/helpers';
import {
  useSalesTeam,
  useSalesTeamAgentOptions,
  useSalesTeams,
  useSaveSalesTeam,
} from '../../hooks/useSalesTeams';
import { useSalesTeamActions } from '../../actions';
import { agentOptionLabel, agentsMovingIn, leftLabel } from '../../lib/moves';
import type { SalesTeamDetail as Detail } from '../../types/salesTeam.types';
import { useSalesTargets } from '../../../targets/hooks/useSalesTargets';
import { foldBySubject } from '../../../targets/lib/fold';
import {
  BASIS_LABEL,
  METRIC_LABEL,
  formatFigure,
  formatPct,
  dateRange,
  scopeSummary,
} from '../../../targets/lib/format';
import type { SalesTargetRow } from '../../../targets/types/salesTarget.types';

/** Metric, counts and scope of a target as pills, the metric first (N4). */
function measurePills(row: SalesTargetRow) {
  if (!row.metric) return [];
  return [
    { key: 'metric', label: METRIC_LABEL[row.metric] },
    { key: 'basis', label: row.basis ? BASIS_LABEL[row.basis] : '' },
    { key: 'scope', label: scopeSummary(row.product_scope, row.scope_labels.length) },
  ].filter((p) => p.label);
}

/** One agent's targets on their row: the first target's name, or a pill per target. */
function AgentTargets({ rows, label }: { rows: SalesTargetRow[]; label: string }) {
  if (rows.length === 1) {
    return (
      <Link
        href={`/sales/targets/${rows[0].target_id}`}
        className="block truncate text-sm text-primary hover:underline"
        title={rows[0].name ?? undefined}
      >
        {rows[0].name}
      </Link>
    );
  }
  return (
    <PillOverflow
      ariaLabel={`Targets of ${label}`}
      items={rows.map((r) => ({ key: r.target_id as string, label: r.name ?? '' }))}
      renderPopover={() => (
        <ul className="flex flex-col gap-1 text-sm">
          {rows.map((r) => (
            <li key={r.target_id} className="flex min-w-0 items-center justify-between gap-3">
              <Link href={`/sales/targets/${r.target_id}`} className="truncate text-primary hover:underline">
                {r.name}
              </Link>
              <span className="shrink-0 tabular-nums">{formatPct(r.achieved_pct)}</span>
            </li>
          ))}
        </ul>
      )}
    />
  );
}

type TeamTab = 'details' | 'targets' | 'agents';

const TEAM_TABS: { value: TeamTab; label: string; icon: typeof Info }[] = [
  { value: 'details', label: 'Details', icon: Info },
  { value: 'targets', label: 'Targets', icon: Target },
  { value: 'agents', label: 'Agents', icon: UsersRound },
];

/** A labelled read-only value, or its input while editing (the same place, S6-13). */
function Field({ label, htmlFor, children }: { label: string; htmlFor?: string; children: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-1">
      {htmlFor ? (
        <Label htmlFor={htmlFor} className="text-xs text-muted-foreground">
          {label}
        </Label>
      ) : (
        <span className="text-xs text-muted-foreground">{label}</span>
      )}
      <div className="min-w-0 text-sm">{children}</div>
    </div>
  );
}

/**
 * A sales team's own page (UAC S6-13, S6-15; owner rulings 26 Sep 06:01 (Lavish) N5 and
 * 26 Sep 06:09 T2; the S1 hand test of 27 Sep, F2).
 *
 * The Users record pattern: a header card (the name, the Active badge, and the agent count,
 * Created and Updated in the meta strip; prev/next, the gear and Set target on the right),
 * then line tabs in the order **Details** (name and leader), **Targets** (every team target
 * of the team) and **Agents** (each agent's line with their own figures on the date). Edit is an
 * item in the gear, not a button of its own; the edit view is this same record, same tabs,
 * each value swapped for its input in place, with Cancel and Save in the header card.
 *
 * The Agents tab's date is the Targets page's `?on=`, today otherwise. An agent who left this
 * month keeps a muted line with a "Left 14 Oct" pill, so the team's figure for the month is
 * explained on screen; each agent is one line, however often they left and came back (owner
 * ruling 26 Sep ~13:05Z). The leader (W1) is named in Details and tagged on their row; in edit
 * the Leader picker offers the agents kept and added in this session only.
 */
export function SalesTeamDetail({ id }: { id: string }) {
  const router = useRouter();
  const params = useSearchParams();
  const on = params.get('on') || todayMalaysiaYyyyMmDd();
  const canEdit = useHasPermission('sales.teams.edit');
  const canSetTarget = useHasPermission('sales.targets.add');
  const { data: team, isLoading, isError } = useSalesTeam(id, on);
  const { data: teamTargets } = useSalesTargets({ all: true, subject: 'team', salesTeamId: id });
  const { data: agentTargets } = useSalesTargets({ on, subject: 'agent', salesTeamId: id });
  const { data: list } = useSalesTeams('');
  const save = useSaveSalesTeam();
  const { actions: teamActions, pending } = useSalesTeamActions(team, {
    onDeleted: () => router.push('/sales/teams'),
  });

  const [tab, setTab] = useState<TeamTab>('details');
  const [isEditing, setIsEditing] = useState(false);
  const [name, setName] = useState('');
  const [isActive, setIsActive] = useState(true);
  const [keptIds, setKeptIds] = useState<string[]>([]);
  const [addIds, setAddIds] = useState<string[]>([]);
  const [leaderId, setLeaderId] = useState('');
  const [movesOn, setMovesOn] = useState(todayMalaysiaYyyyMmDd());
  const { data: options = [] } = useSalesTeamAgentOptions(isEditing);

  const teams = list?.data ?? [];
  const index = teams.findIndex((t) => t.id === id);

  const teamLines = useMemo(
    () => (teamTargets?.rows ?? []).filter((r) => r.target_id && r.sales_team_id === id),
    [teamTargets, id],
  );
  const agentLines = useMemo(() => {
    const folded = foldBySubject(
      (agentTargets?.rows ?? [])
        .filter((r) => r.target_id && r.sales_agent_id)
        .map((r) => ({ ...r, subject_key: r.sales_agent_id as string, end_date: r.end_date ?? null })),
    );
    return new Map(folded.map((f) => [f.subject_key, f]));
  }, [agentTargets]);

  const beginEdit = (current: Detail) => {
    setName(current.name);
    setIsActive(current.is_active);
    setKeptIds(current.members.filter((m) => !m.left).map((m) => m.sales_agent_id));
    setAddIds([]);
    setLeaderId(current.leader_sales_agent_id ?? '');
    setMovesOn(todayMalaysiaYyyyMmDd());
    setIsEditing(true);
  };

  const removeAgent = (agentId: string) => {
    setKeptIds((ids) => ids.filter((i) => i !== agentId));
    if (leaderId === agentId) setLeaderId('');
  };
  const pickAddIds = (ids: string[]) => {
    setAddIds(ids);
    if (!keptIds.includes(leaderId) && !ids.includes(leaderId)) setLeaderId('');
  };

  const addOptions = useMemo(
    () =>
      options
        .filter((o) => !keptIds.includes(o.id))
        .map((o) => ({ value: o.id, label: agentOptionLabel(o, id) })),
    [options, keptIds, id],
  );
  const moving = agentsMovingIn(addIds, options, id);
  const leaderOptions = useMemo(
    () =>
      [...keptIds, ...addIds].flatMap((agentId) => {
        const label =
          team?.members.find((m) => m.sales_agent_id === agentId)?.label ??
          options.find((o) => o.id === agentId)?.label;
        return label ? [{ value: agentId, label }] : [];
      }),
    [keptIds, addIds, team, options],
  );

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-24 w-full rounded-xl" />
        <Skeleton className="h-48 w-full rounded-xl" />
      </div>
    );
  }

  if (isError || !team) {
    return (
      <Card className="flex flex-col items-center gap-3 p-10 text-center">
        <div className="text-sm font-semibold">Sales team not found</div>
        <p className="max-w-md text-sm text-muted-foreground">
          This team does not exist, or it was deleted after this link was made.
        </p>
      </Card>
    );
  }

  const active = team.members.filter((m) => !m.left);
  const left = team.members.filter((m) => m.left);
  const shownActive = isEditing ? active.filter((m) => keptIds.includes(m.sales_agent_id)) : active;
  const canSave = name.trim().length > 0 && (moving.length === 0 || !!movesOn) && !save.isPending;
  const isEmpty = shownActive.length === 0 && left.length === 0;

  const handleSave = async () => {
    if (!canSave) return;
    try {
      await save.mutateAsync({
        teamId: team.id,
        name: name.trim(),
        is_active: isActive,
        sales_agent_ids: [...keptIds, ...addIds],
        ...(moving.length ? { moves_on: movesOn } : {}),
        leader_sales_agent_id: leaderId || null,
      });
      setIsEditing(false);
    } catch {
      // The hook toasted the reason; the session stays open so nothing typed is lost.
    }
  };

  const newTargetHref = (kind: 'team' | 'agent', subjectId: string) =>
    `/sales/targets/new?kind=${kind}&subject=${subjectId}`;
  const setTeamTarget = () => router.push(newTargetHref('team', team.id));
  const startAddAgents = () => {
    beginEdit(team);
    setTab('agents');
  };

  // Edit leads the gear (F2); Delete stays last, in red.
  const actions: RecordAction[] = canEdit
    ? [{ key: 'sales_team.edit', label: 'Edit', icon: SquarePen, run: () => beginEdit(team) }, ...teamActions]
    : teamActions;
  const agentCount = `${team.member_count} agent${team.member_count === 1 ? '' : 's'}`;

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader className="block py-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="flex min-w-0 flex-col gap-1.5">
              <div className="flex min-w-0 flex-wrap items-center gap-3">
                <h2 className="truncate text-lg font-semibold" title={team.name}>
                  {team.name}
                </h2>
                {isEditing ? (
                  <span className="flex items-center gap-2">
                    <Switch
                      id="sales-team-edit-active"
                      aria-label="Active"
                      checked={isActive}
                      onCheckedChange={setIsActive}
                    />
                    <Label htmlFor="sales-team-edit-active">Active</Label>
                  </span>
                ) : (
                  <Badge variant={team.is_active ? 'success' : 'secondary'} appearance="light">
                    <BadgeDot />
                    {team.is_active ? 'Active' : 'Inactive'}
                  </Badge>
                )}
              </div>
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                <span>{agentCount}</span>
                {left.length ? <span>{`${left.length} left this month`}</span> : null}
                {team.created_at ? <span>Created {formatDateInMalaysia(team.created_at)}</span> : null}
                {team.updated_at ? <span>Updated {formatDateInMalaysia(team.updated_at)}</span> : null}
              </div>
            </div>
            {isEditing ? (
              <div className="flex shrink-0 flex-wrap items-center gap-2">
                <Button variant="outline" size="sm" onClick={() => setIsEditing(false)} disabled={save.isPending}>
                  Cancel
                </Button>
                <Button size="sm" onClick={handleSave} disabled={!canSave}>
                  {save.isPending ? <LoaderCircleIcon className="size-4 animate-spin" /> : null}
                  Save
                </Button>
              </div>
            ) : (
              <DetailActions
                pagerNode={
                  <RecordNavigation
                    index={index >= 0 ? index + 1 : null}
                    total={teams.length}
                    hasPrevious={index > 0}
                    hasNext={index >= 0 && index < teams.length - 1}
                    onPrevious={() => router.push(`/sales/teams/${teams[index - 1].id}`)}
                    onNext={() => router.push(`/sales/teams/${teams[index + 1].id}`)}
                    ariaLabel="sales team"
                  />
                }
                actions={actions}
                pendingAction={pending}
                gearLabel="Sales team options"
                primary={
                  canSetTarget ? (
                    <Button variant="primary" size="sm" className="gap-1.5" onClick={setTeamTarget}>
                      <Target className="size-4" />
                      Set target
                    </Button>
                  ) : undefined
                }
              />
            )}
          </div>
        </CardHeader>
      </Card>

      <Tabs value={tab} onValueChange={(v) => setTab(v as TeamTab)}>
        <TabsList variant="line" className="mb-5">
          {TEAM_TABS.map((t) => (
            <TabsTrigger key={t.value} value={t.value} onClick={() => setTab(t.value)}>
              <t.icon className="size-4" />
              <span>{t.label}</span>
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="details">
          <Card>
            <section aria-label="Details" className="grid grid-cols-1 gap-4 p-5 sm:grid-cols-2">
              <Field label="Team name" htmlFor={isEditing ? 'sales-team-edit-name' : undefined}>
                {isEditing ? (
                  <Input
                    id="sales-team-edit-name"
                    value={name}
                    maxLength={120}
                    onChange={(e) => setName(e.target.value)}
                    className="h-8"
                  />
                ) : (
                  <span className="block truncate" title={team.name}>
                    {team.name}
                  </span>
                )}
              </Field>
              <Field label="Leader" htmlFor={isEditing ? 'sales-team-edit-leader' : undefined}>
                {isEditing ? (
                  <SearchableSelect
                    id="sales-team-edit-leader"
                    value={leaderId}
                    onChange={setLeaderId}
                    options={leaderOptions}
                    placeholder="No leader"
                    emptyMessage="No agents in this team."
                    clearable
                    wrapOptions
                  />
                ) : (
                  <span className="block truncate" title={team.leader_label ?? undefined}>
                    {team.leader_label ?? 'No leader'}
                  </span>
                )}
              </Field>
            </section>
          </Card>
        </TabsContent>

        <TabsContent value="targets">
          <Card>
            <section aria-label="Team targets" className="flex flex-col gap-3 p-5">
              {teamLines.length === 0 ? (
                <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed py-8 text-center">
                  <span className="text-sm font-medium">No team target</span>
                  {/* Outline: the header's Set target is the page's one primary action. */}
                  {canSetTarget ? (
                    <Button variant="outline" size="sm" onClick={setTeamTarget}>
                      <Plus className="size-4" />
                      Set target
                    </Button>
                  ) : null}
                </div>
              ) : (
                <ul className="flex flex-col divide-y rounded-lg border">
                  {teamLines.map((row) => (
                    <li
                      key={row.target_id}
                      className="grid min-w-0 grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1 px-3 py-2 sm:grid-cols-[6.5rem_minmax(0,2fr)_minmax(0,1.5fr)_minmax(0,1.6fr)_6rem_6rem_4rem]"
                    >
                      <span className="hidden truncate text-xs text-muted-foreground sm:block">{row.target_no}</span>
                      <Link
                        href={`/sales/targets/${row.target_id}`}
                        className="truncate text-sm text-primary hover:underline"
                        title={row.name ?? undefined}
                      >
                        {row.name}
                      </Link>
                      <span className="hidden min-w-0 sm:block">
                        <PillOverflow
                          ariaLabel={`What ${row.name} counts`}
                          items={measurePills(row)}
                          renderPopover={(items) => (
                            <ul className="flex flex-col gap-1 text-sm">
                              {items.map((i) => (
                                <li key={i.key}>{i.label}</li>
                              ))}
                              {row.scope_labels.map((label) => (
                                <li key={label} className="truncate text-muted-foreground" title={label}>
                                  {label}
                                </li>
                              ))}
                            </ul>
                          )}
                        />
                      </span>
                      <span className="hidden truncate text-xs text-muted-foreground sm:block">
                        {dateRange(row.start_date, row.end_date)}
                      </span>
                      <span className="hidden text-end text-sm tabular-nums sm:block">{formatFigure(row.target_value)}</span>
                      <span className="hidden text-end text-sm tabular-nums sm:block">{formatFigure(row.achieved_value)}</span>
                      <span className="text-end text-sm font-medium tabular-nums">{formatPct(row.achieved_pct)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </Card>
        </TabsContent>

        <TabsContent value="agents">
          <Card>
            <section aria-label="Agents" className="flex flex-col gap-3 p-5">
              {canEdit && !isEditing && !isEmpty ? (
                <div className="flex justify-end">
                  <Button variant="outline" size="sm" onClick={startAddAgents}>
                    <Plus className="size-4" />
                    Add agents
                  </Button>
                </div>
              ) : null}

              {isEditing ? (
                <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
                  <div className="flex min-w-0 flex-1 flex-col gap-1.5">
                    <Label htmlFor="sales-team-add-agents">Add agents</Label>
                    <SearchableMultiSelect
                      id="sales-team-add-agents"
                      value={addIds}
                      onChange={pickAddIds}
                      options={addOptions}
                      placeholder="Pick agents"
                      emptyMessage="No other active sales agents."
                      wrapOptions
                    />
                  </div>
                  {moving.length ? (
                    <div className="flex flex-col gap-1.5">
                      <Label htmlFor="sales-team-edit-moves-on">Moves on</Label>
                      <Input
                        id="sales-team-edit-moves-on"
                        type="date"
                        required
                        max={todayMalaysiaYyyyMmDd()}
                        value={movesOn}
                        onChange={(e) => setMovesOn(e.target.value)}
                        className="w-44"
                      />
                    </div>
                  ) : null}
                </div>
              ) : null}

              {isEmpty ? (
                <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed py-8 text-center">
                  <span className="text-sm font-medium">No agents in this team</span>
                  {canEdit && !isEditing ? (
                    <Button variant="outline" size="sm" onClick={startAddAgents}>
                      <Plus className="size-4" />
                      Add agents
                    </Button>
                  ) : null}
                </div>
              ) : (
                <ul className="flex flex-col divide-y rounded-lg border">
                  {shownActive.map((m) => (
                    <li key={m.sales_agent_id} className="flex min-w-0 items-center justify-between gap-2 px-3 py-2">
                      <span className="flex min-w-0 items-center gap-2">
                        <span className="truncate text-sm" title={m.label}>
                          {m.label}
                        </span>
                        {m.sales_agent_id === (isEditing ? leaderId : team.leader_sales_agent_id) ? (
                          <Badge variant="primary" appearance="light" size="sm">
                            Leader
                          </Badge>
                        ) : null}
                      </span>
                      <AgentFigures
                        line={agentLines.get(m.sales_agent_id)}
                        label={m.label}
                        canSetTarget={canSetTarget && !isEditing}
                        onSetTarget={() => router.push(newTargetHref('agent', m.sales_agent_id))}
                      />
                      {isEditing ? (
                        <Button
                          variant="ghost"
                          size="sm"
                          mode="icon"
                          aria-label={`Remove ${m.label}`}
                          onClick={() => removeAgent(m.sales_agent_id)}
                        >
                          <X className="size-4" />
                        </Button>
                      ) : null}
                    </li>
                  ))}
                  {left.map((m) => (
                    <li
                      key={`left-${m.sales_agent_id}-${m.valid_to}`}
                      data-left="true"
                      className="flex min-w-0 items-center gap-2 px-3 py-2 text-muted-foreground"
                    >
                      <span className="truncate text-sm" title={m.label}>
                        {m.label}
                      </span>
                      {m.valid_to ? (
                        <Badge variant="warning" appearance="light" size="sm">
                          {leftLabel(m.valid_to)}
                        </Badge>
                      ) : null}
                      <AgentFigures line={agentLines.get(m.sales_agent_id)} label={m.label} canSetTarget={false} />
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

/**
 * An agent's figures on their row (S1): their targets, then the first target's Target,
 * Achieved and %. A member who left in the period shows their OWN target, muted with the Left
 * pill, which is why a team's achieved can differ from the sum of these lines (plan 16.3).
 */
function AgentFigures({
  line,
  label,
  canSetTarget,
  onSetTarget,
}: {
  line: { primary: SalesTargetRow; targets: SalesTargetRow[] } | undefined;
  label: string;
  canSetTarget: boolean;
  onSetTarget?: () => void;
}) {
  if (!line) {
    return (
      <span className="ms-auto flex shrink-0 items-center gap-2">
        <span className="text-xs text-muted-foreground">No target</span>
        {canSetTarget && onSetTarget ? (
          <Button variant="outline" size="sm" className="h-7" onClick={onSetTarget}>
            Set target
          </Button>
        ) : null}
      </span>
    );
  }
  return (
    <span className="ms-auto flex min-w-0 items-center justify-end gap-3">
      <span className="hidden min-w-0 max-w-[14rem] sm:block">
        <AgentTargets rows={line.targets} label={label} />
      </span>
      <span className="hidden w-24 text-end text-sm tabular-nums md:block">{formatFigure(line.primary.target_value)}</span>
      <span className="hidden w-24 text-end text-sm tabular-nums md:block">{formatFigure(line.primary.achieved_value)}</span>
      <span className="w-14 shrink-0 text-end text-sm font-medium tabular-nums">{formatPct(line.primary.achieved_pct)}</span>
    </span>
  );
}
