'use client';

import * as React from 'react';
import { Info, X } from 'lucide-react';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { useMcpToolsForPicker } from '../hooks/useAccessAgents';

export interface McpToolSelectorProps {
  value: string[];
  onChange: (next: string[]) => void;
  /** Agent currently being edited; tools already linked to OTHER agents are
   *  badged with the list of co-owners (many-to-many — adding does NOT remove
   *  other agents). */
  currentAgentId?: string;
  disabled?: boolean;
}

type Row = {
  id: string;
  tool_name: string;
  module_key: string;
  description: string | null;
  otherOwners: string[];
};

export function McpToolSelector({
  value,
  onChange,
  currentAgentId,
  disabled,
}: McpToolSelectorProps) {
  const { data, isLoading } = useMcpToolsForPicker();

  const rows: Row[] = React.useMemo(() => {
    return (data ?? []).map((r) => {
      const ids = r.current_agent_ids ?? [];
      const names = r.current_agent_names ?? [];
      const otherOwners = names.filter((_, idx) => ids[idx] !== currentAgentId);
      return {
        id: r.id,
        tool_name: r.tool_name,
        module_key: r.module_key || 'Unbound',
        description: r.description ?? null,
        otherOwners,
      };
    });
  }, [data, currentAgentId]);

  const byId = React.useMemo(() => {
    const m = new Map<string, Row>();
    for (const r of rows) m.set(r.id, r);
    return m;
  }, [rows]);

  const selectedSet = React.useMemo(() => new Set(value), [value]);
  const selectedRows = React.useMemo(
    () => value.map((id) => byId.get(id)).filter((r): r is Row => !!r),
    [value, byId],
  );

  const toggle = (id: string) => {
    if (selectedSet.has(id)) onChange(value.filter((x) => x !== id));
    else onChange([...value, id]);
  };

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Loading MCP tools...</p>;
  }
  if (rows.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No MCP tools registered yet — modules with{' '}
        <code className="font-mono text-xs">mcp/tools.json</code> populate this list on upload.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <SearchableMultiSelect
        value={value}
        onChange={onChange}
        disabled={disabled}
        placeholder="Select MCP tools..."
        emptyMessage="No MCP tools match."
        // Chips live in the panel below (they carry description tooltips), so the trigger
        // stays a plain count as it was.
        renderTriggerLabel={(sel) => (sel.length === 0 ? 'Select MCP tools...' : `${sel.length} selected`)}
        options={rows.map((r) => ({
          value: r.id,
          label: r.tool_name,
          group: r.module_key,
          searchText: `${r.tool_name} ${r.module_key}`,
          description: r.description ?? undefined,
          badgeText: r.otherOwners.length > 0 ? `also: ${r.otherOwners.join(', ')}` : undefined,
        }))}
        // The per-row description is an interactive tooltip, not plain text, so the row body
        // is rendered here rather than via `description`.
        renderOption={(opt) => {
          const row = byId.get(opt.value);
          return (
            <div className="flex flex-1 items-center gap-2">
              <span className="flex-1 truncate font-mono text-xs">{opt.label}</span>
              {opt.badgeText ? (
                <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] text-amber-900">
                  {opt.badgeText}
                </span>
              ) : null}
              {row?.description ? (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span
                      role="button"
                      tabIndex={-1}
                      onClick={(e) => {
                        e.stopPropagation();
                        e.preventDefault();
                      }}
                      onPointerDown={(e) => e.stopPropagation()}
                      className="inline-flex size-5 items-center justify-center rounded text-muted-foreground hover:bg-muted hover:text-foreground"
                      aria-label="Show description"
                    >
                      <Info className="size-3.5" />
                    </span>
                  </TooltipTrigger>
                  <TooltipContent
                    side="right"
                    align="start"
                    className="max-w-sm whitespace-pre-wrap break-words text-xs leading-snug"
                  >
                    {row.description}
                  </TooltipContent>
                </Tooltip>
              ) : null}
            </div>
          );
        }}
      />

      {selectedRows.length > 0 ? (
        <div className="flex flex-wrap gap-1.5 rounded-md border border-dashed border-input p-2">
          {selectedRows.map((r) => (
            <span
              key={r.id}
              className="inline-flex items-center gap-1 rounded-md bg-secondary px-2 py-1 text-xs"
            >
              <span className="font-mono">{r.tool_name}</span>
              {r.description ? (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      type="button"
                      className="inline-flex size-4 items-center justify-center rounded text-muted-foreground hover:text-foreground"
                      aria-label="Show description"
                    >
                      <Info className="size-3" />
                    </button>
                  </TooltipTrigger>
                  <TooltipContent
                    side="top"
                    className="max-w-sm whitespace-pre-wrap break-words text-xs leading-snug"
                  >
                    {r.description}
                  </TooltipContent>
                </Tooltip>
              ) : null}
              <button
                type="button"
                onClick={() => toggle(r.id)}
                disabled={disabled}
                className="ml-0.5 inline-flex size-4 items-center justify-center rounded text-muted-foreground hover:bg-muted-foreground/10 hover:text-foreground disabled:opacity-50"
                aria-label={`Remove ${r.tool_name}`}
              >
                <X className="size-3" />
              </button>
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}
