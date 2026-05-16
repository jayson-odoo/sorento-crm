'use client';

import * as React from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useMcpToolsForPicker, useTeams } from '../hooks/useAccessAgents';
import type { McpToolBindingInput } from '../services/accessAgentService';

export interface McpToolBindingsEditorProps {
  value: McpToolBindingInput[];
  onChange: (next: McpToolBindingInput[]) => void;
  disabled?: boolean;
}

const NO_TEAM = '__legacy__';

export function McpToolBindingsEditor({
  value,
  onChange,
  disabled,
}: McpToolBindingsEditorProps) {
  const { data: tools, isLoading: toolsLoading } = useMcpToolsForPicker();
  const { data: teams, isLoading: teamsLoading } = useTeams();

  const toolOptions = React.useMemo(() => tools ?? [], [tools]);
  const teamOptions = React.useMemo(() => teams ?? [], [teams]);

  const updateRow = (idx: number, patch: Partial<McpToolBindingInput>) => {
    const next = value.map((row, i) => (i === idx ? { ...row, ...patch } : row));
    onChange(next);
  };
  const removeRow = (idx: number) => {
    onChange(value.filter((_, i) => i !== idx));
  };
  const addRow = () => {
    onChange([
      ...value,
      { tool_id: toolOptions[0]?.id ?? '', team_id: null, tier: null },
    ]);
  };

  if (toolsLoading || teamsLoading) {
    return <p className="text-sm text-muted-foreground">Loading tools and teams...</p>;
  }
  if (toolOptions.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No MCP tools registered. Modules with{' '}
        <code className="font-mono text-xs">mcp/tools.json</code> populate the catalog on
        upload.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-[1fr_1fr_120px_44px] gap-2 text-xs font-medium text-muted-foreground">
        <span>Tool</span>
        <span>Team</span>
        <span>Tier</span>
        <span />
      </div>
      {value.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No bindings. Click <span className="font-mono">Add binding</span> to map a tool
          to a team. Leave team empty for legacy routing through this agent&apos;s team
          set.
        </p>
      ) : null}
      {value.map((row, idx) => (
        <div
          key={idx}
          className="grid grid-cols-[1fr_1fr_120px_44px] gap-2 items-center"
        >
          <Select
            value={row.tool_id || undefined}
            onValueChange={(v) => updateRow(idx, { tool_id: v })}
            disabled={disabled}
          >
            <SelectTrigger>
              <SelectValue placeholder="Select tool..." />
            </SelectTrigger>
            <SelectContent>
              {toolOptions.map((t) => (
                <SelectItem key={t.id} value={t.id}>
                  <span className="font-mono text-xs">{t.tool_name}</span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select
            value={row.team_id ?? NO_TEAM}
            onValueChange={(v) =>
              updateRow(idx, { team_id: v === NO_TEAM ? null : v })
            }
            disabled={disabled}
          >
            <SelectTrigger>
              <SelectValue placeholder="Select team..." />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NO_TEAM}>
                <span className="text-muted-foreground">— legacy (any team) —</span>
              </SelectItem>
              {teamOptions.map((t) => (
                <SelectItem key={t.id} value={t.id}>
                  {t.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Input
            type="number"
            min={1}
            max={3}
            value={row.tier ?? ''}
            placeholder="tier"
            disabled={disabled}
            onChange={(e) => {
              const raw = e.target.value;
              if (raw === '') {
                updateRow(idx, { tier: null });
                return;
              }
              const n = Number(raw);
              updateRow(idx, {
                tier: Number.isInteger(n) && n >= 1 && n <= 3 ? n : null,
              });
            }}
          />
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={() => removeRow(idx)}
            disabled={disabled}
            aria-label="Remove binding"
          >
            <Trash2 className="size-4" />
          </Button>
        </div>
      ))}
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={addRow}
        disabled={disabled}
      >
        <Plus className="mr-2 size-4" />
        Add binding
      </Button>
    </div>
  );
}
