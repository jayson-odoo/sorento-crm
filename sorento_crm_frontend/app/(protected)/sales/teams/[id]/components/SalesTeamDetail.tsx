'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { LoaderCircleIcon, Plus, SquarePen, Target, X } from 'lucide-react';
import { Badge, BadgeDot } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardHeader } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { Switch } from '@/components/ui/switch';
import DetailActions from '@/components/common/DetailActions';
import { PillOverflow } from '@/components/common/PillOverflow';
import RecordNavigation from '@/components/common/RecordNavigation';
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
import SetTargetModal from '../../../targets/components/SetTargetModal';
import { foldBySubject } from '../../../targets/lib/fold';
import {
  BASIS_LABEL,
  METRIC_LABEL,
  formatFigure,
  formatPct,
  scopeSummary,
  shortDate,
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

/**
 * A sales team's own page (UAC S6-13, S6-15; owner rulings 26 Sep 06:01 (Lavish) N5 and
 * 26 Sep 06:09 T2).
 *
 * VIEW AND EDIT ARE THE SAME LAYOUT. Edit swaps the name for an input and the Active badge
 * for a switch, in place, and gives the Agents section an Add agents picker and a remove
 * control per row; nothing moves. Read-only metadata (agent count, Created, Updated) sits in
 * the header's meta strip.
 *
 * Two sections, in order, always rendered (S6-13, S1): **Team targets** (one line per team
 * target active on the date, "No team target" with Set target) and **Agents**, each agent's
 * line carrying their own targets and the first one's Target, Achieved and %. The date is the
 * Targets page's Active on (`?on=`), today otherwise. An agent who left this month keeps a
 * muted line with a "Left 14 Oct" pill, so the team's figure for the month is explained on
 * screen. Set target is the header's primary action and presets this team (plan 3.9), Edit
 * the secondary one; on an agent's line, Set target presets that agent.
 * Each agent is one line, however often they left and came back (owner ruling 26 Sep ~13:05Z).
 *
 * The leader (owner ruling 26 Sep ~13:25Z, W1) is named on its own line under the team name,
 * and their row carries a "Leader" tag. In edit that line becomes the Leader picker, offering
 * the agents kept and added in this session only; removing the leader clears it.
 */
export function SalesTeamDetail({ id }: { id: string }) {
  const router = useRouter();
  const params = useSearchParams();
  // The Targets page's Active on date, carried in the URL; today when opened any other way.
  const on = params.get('on') || todayMalaysiaYyyyMmDd();
  const canEdit = useHasPermission('sales.teams.edit');
  const canSetTarget = useHasPermission('sales.targets.add');
  const { data: team, isLoading, isError } = useSalesTeam(id, on);
  const { data: teamTargets } = useSalesTargets({ on, subject: 'team', salesTeamId: id });
  const { data: agentTargets } = useSalesTargets({ on, subject: 'agent', salesTeamId: id });
  const [setTarget, setSetTarget] = useState<{ kind: 'agent' | 'team'; subjectId: string } | null>(null);
  const { data: list } = useSalesTeams('');
  const save = useSaveSalesTeam();
  const { actions, pending } = useSalesTeamActions(team, {
    onDeleted: () => router.push('/sales/teams'),
  });

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

  // Team targets active on the date, one line each; an agent's own targets folded to one line.
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

  const agentCount = `${team.member_count} agent${team.member_count === 1 ? '' : 's'}`;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="block py-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="flex min-w-0 flex-col gap-2">
              <div className="flex min-w-0 flex-wrap items-center gap-3">
                {isEditing ? (
                  <div className="flex flex-col gap-1">
                    <Label htmlFor="sales-team-edit-name" className="text-xs text-muted-foreground">
                      Team name
                    </Label>
                    <Input
                      id="sales-team-edit-name"
                      value={name}
                      maxLength={120}
                      onChange={(e) => setName(e.target.value)}
                      className="h-8 w-64 max-w-full"
                    />
                  </div>
                ) : (
                  <h2 className="truncate text-lg font-semibold" title={team.name}>
                    {team.name}
                  </h2>
                )}
                {isEditing ? (
                  <div className="flex items-center gap-2">
                    <Switch
                      id="sales-team-edit-active"
                      aria-label="Active"
                      checked={isActive}
                      onCheckedChange={setIsActive}
                    />
                    <Label htmlFor="sales-team-edit-active">Active</Label>
                  </div>
                ) : (
                  <Badge variant={team.is_active ? 'success' : 'secondary'} appearance="light">
                    <BadgeDot />
                    {team.is_active ? 'Active' : 'Inactive'}
                  </Badge>
                )}
              </div>
              {isEditing ? (
                <div className="flex flex-col gap-1">
                  <Label htmlFor="sales-team-edit-leader" className="text-xs text-muted-foreground">
                    Leader
                  </Label>
                  <SearchableSelect
                    id="sales-team-edit-leader"
                    value={leaderId}
                    onChange={setLeaderId}
                    options={leaderOptions}
                    placeholder="No leader"
                    emptyMessage="No agents in this team."
                    clearable
                    wrapOptions
                    className="w-64 max-w-full"
                  />
                </div>
              ) : (
                <div className="truncate text-sm" title={team.leader_label ?? undefined}>
                  {team.leader_label ? `Leader: ${team.leader_label}` : 'No leader'}
                </div>
              )}
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
              <div className="flex shrink-0 flex-wrap items-center gap-2">
              {/* Edit is the secondary action (plan 3.9, team form view); it steps aside while a
                  delete is counting down, as DetailActions' own primary does. */}
              {canEdit && !pending ? (
                <Button variant="outline" size="sm" className="gap-1.5" onClick={() => beginEdit(team)}>
                  <SquarePen className="size-4" />
                  Edit
                </Button>
              ) : null}
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
                primary={
                  canSetTarget ? (
                    <Button
                      variant="primary"
                      size="sm"
                      className="gap-1.5"
                      onClick={() => setSetTarget({ kind: 'team', subjectId: team.id })}
                    >
                      <Target className="size-4" />
                      Set target
                    </Button>
                  ) : undefined
                }
              />
              </div>
            )}
          </div>
        </CardHeader>
      </Card>

      <Card>
        <section aria-label="Team targets" className="flex flex-col gap-3 p-4">
          <h3 className="text-sm font-semibold">Team targets</h3>
          {teamLines.length === 0 ? (
            <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed py-8 text-center">
              <span className="text-sm font-medium">No team target</span>
              {/* Outline: the header's Set target is the page's one primary action. */}
              {canSetTarget ? (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setSetTarget({ kind: 'team', subjectId: team.id })}
                >
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
                  className="grid min-w-0 grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1 px-3 py-2 sm:grid-cols-[minmax(0,2fr)_minmax(0,1.5fr)_7rem_6rem_6rem_4rem]"
                >
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
                    {row.period_end ? `to ${shortDate(row.end_date ?? row.period_end)}` : ''}
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

      <Card>
        <section aria-label="Agents" className="flex flex-col gap-3 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-sm font-semibold">Agents</h3>
            {canEdit && !isEditing && !isEmpty ? (
              <Button variant="outline" size="sm" onClick={() => beginEdit(team)}>
                <Plus className="size-4" />
                Add agents
              </Button>
            ) : null}
          </div>

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
                <Button variant="primary" size="sm" onClick={() => beginEdit(team)}>
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
                    onSetTarget={() => setSetTarget({ kind: 'agent', subjectId: m.sales_agent_id })}
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
      {setTarget ? (
        <SetTargetModal
          open
          onOpenChange={(open) => (open ? null : setSetTarget(null))}
          presetKind={setTarget.kind}
          presetSubjectId={setTarget.subjectId}
        />
      ) : null}
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
