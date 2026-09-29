'use client';

import { useEffect, useMemo, useState } from 'react';
import { LoaderCircleIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { todayMalaysiaYyyyMmDd } from '@/lib/helpers';
import { useSalesTeamAgentOptions, useSaveSalesTeam } from '../hooks/useSalesTeams';
import { agentOptionLabel, agentsMovingIn } from '../lib/moves';

/**
 * The Add team modal (UAC S6-12, owner ruling 26 Sep 06:01 (Lavish), N2): Name,
 * Agents (the standard multi-select of active agents, each option saying which team the agent
 * is in now, N8), Active. Moves on appears only when a picked agent is in another team
 * (S6-15, T2): a date, today by default, never later than today, never empty. Leader
 * (owner ruling 26 Sep ~13:25Z, W1) offers only the picked agents, and clears when its agent
 * is unpicked.
 * Editing a team is in place on its page (S6-13), not here.
 */
export default function SalesTeamModal({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const teamId = null;
  const { data: options = [] } = useSalesTeamAgentOptions(open);
  const save = useSaveSalesTeam();

  const [name, setName] = useState('');
  const [agentIds, setAgentIds] = useState<string[]>([]);
  const [leaderId, setLeaderId] = useState('');
  const [isActive, setIsActive] = useState(true);
  const [movesOn, setMovesOn] = useState(todayMalaysiaYyyyMmDd());

  useEffect(() => {
    if (!open) return;
    setName('');
    setAgentIds([]);
    setLeaderId('');
    setIsActive(true);
    setMovesOn(todayMalaysiaYyyyMmDd());
  }, [open]);

  const selectOptions = useMemo(
    () => options.map((o) => ({ value: o.id, label: agentOptionLabel(o, teamId) })),
    [options],
  );
  const leaderOptions = useMemo(
    () =>
      agentIds.flatMap((agentId) => {
        const option = options.find((o) => o.id === agentId);
        return option ? [{ value: option.id, label: option.label }] : [];
      }),
    [agentIds, options],
  );
  const pickAgents = (ids: string[]) => {
    setAgentIds(ids);
    if (!ids.includes(leaderId)) setLeaderId('');
  };
  const moving = agentsMovingIn(agentIds, options, teamId);
  const today = todayMalaysiaYyyyMmDd();
  const canSave = name.trim().length > 0 && (moving.length === 0 || !!movesOn) && !save.isPending;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!canSave) return;
    try {
      await save.mutateAsync({
        teamId,
        name: name.trim(),
        is_active: isActive,
        sales_agent_ids: agentIds,
        ...(moving.length ? { moves_on: movesOn } : {}),
        leader_sales_agent_id: leaderId || null,
      });
      onOpenChange(false);
    } catch {
      // The hook toasted the reason; the modal stays open with what was typed.
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add team</DialogTitle>
        </DialogHeader>
        <form onSubmit={submit} className="flex flex-col gap-4">
          <DialogBody className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="sales-team-name">Name</Label>
              <Input
                id="sales-team-name"
                value={name}
                maxLength={120}
                onChange={(e) => setName(e.target.value)}
                autoFocus
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="sales-team-agents">Agents</Label>
              <SearchableMultiSelect
                id="sales-team-agents"
                value={agentIds}
                onChange={pickAgents}
                options={selectOptions}
                placeholder="Pick agents"
                emptyMessage="No active sales agents."
                wrapOptions
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="sales-team-leader">Leader</Label>
              <SearchableSelect
                id="sales-team-leader"
                value={leaderId}
                onChange={setLeaderId}
                options={leaderOptions}
                placeholder="No leader"
                emptyMessage="Pick agents first."
                clearable
                wrapOptions
              />
            </div>
            {moving.length > 0 ? (
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="sales-team-moves-on">Moves on</Label>
                <Input
                  id="sales-team-moves-on"
                  type="date"
                  required
                  max={today}
                  value={movesOn}
                  onChange={(e) => setMovesOn(e.target.value)}
                  className="w-44"
                />
              </div>
            ) : null}
            <div className="flex items-center gap-2">
              <Switch id="sales-team-active" aria-label="Active" checked={isActive} onCheckedChange={setIsActive} />
              <Label htmlFor="sales-team-active">Active</Label>
            </div>
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!canSave}>
              {save.isPending ? <LoaderCircleIcon className="size-4 animate-spin" /> : null}
              Save
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
