'use client';

import * as React from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { SearchableSelect } from '@/components/common/SearchableSelect';
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
          <SearchableSelect
            value={row.tool_id || ''}
            onChange={(v) => updateRow(idx, { tool_id: v })}
            disabled={disabled}
            placeholder="Select tool..."
            options={toolOptions.map((t) => ({ value: t.id, label: t.tool_name }))}
            // Tool names are identifiers; keep them monospaced as before.
            renderOption={(opt) => <span className="font-mono text-xs">{opt.label}</span>}
            renderTriggerLabel={(opt) => <span className="font-mono text-xs">{opt.label}</span>}
          />
          <SearchableSelect
            value={row.team_id ?? NO_TEAM}
            onChange={(v) => updateRow(idx, { team_id: v === NO_TEAM ? null : v })}
            disabled={disabled}
            placeholder="Select team..."
            options={[
              { value: NO_TEAM, label: '— legacy (any team) —' },
              ...teamOptions.map((t) => ({ value: t.id, label: t.name })),
            ]}
            renderOption={(opt) =>
              opt.value === NO_TEAM ? (
                <span className="text-muted-foreground">{opt.label}</span>
              ) : (
                <span>{opt.label}</span>
              )
            }
          />
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
