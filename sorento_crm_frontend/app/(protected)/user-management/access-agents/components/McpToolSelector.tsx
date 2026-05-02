'use client';

import * as React from 'react';
import { Check, ChevronDown, Info, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
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
  const [open, setOpen] = React.useState(false);

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

  const grouped = React.useMemo(() => {
    const map = new Map<string, Row[]>();
    for (const r of rows) {
      if (!map.has(r.module_key)) map.set(r.module_key, []);
      map.get(r.module_key)!.push(r);
    }
    return Array.from(map.entries());
  }, [rows]);

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
      <Popover open={open} onOpenChange={(o) => !disabled && setOpen(o)}>
        <PopoverTrigger asChild>
          <button
            type="button"
            disabled={disabled}
            className={cn(
              'flex h-10 w-full items-center justify-between gap-2 rounded-md border border-input bg-background px-3 py-2 text-sm shadow-xs transition-[color,box-shadow] outline-none',
              'focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]',
              'data-[state=open]:border-ring',
              disabled && 'cursor-not-allowed opacity-50',
            )}
          >
            <span className={cn('truncate', value.length === 0 && 'text-muted-foreground')}>
              {value.length === 0 ? 'Select MCP tools...' : `${value.length} selected`}
            </span>
            <ChevronDown className="size-4 opacity-50" />
          </button>
        </PopoverTrigger>
        <PopoverContent className="w-[--radix-popover-trigger-width] p-0" align="start">
          <Command shouldFilter>
            <CommandInput placeholder="Search by name or module..." />
            <CommandList>
              <CommandEmpty>No MCP tools match.</CommandEmpty>
              {grouped.map(([groupKey, opts]) => (
                <CommandGroup key={groupKey} heading={groupKey}>
                  {opts.map((opt) => {
                    const isSelected = selectedSet.has(opt.id);
                    return (
                      <CommandItem
                        key={opt.id}
                        value={`${opt.tool_name} ${opt.module_key}`}
                        onSelect={() => toggle(opt.id)}
                        className="flex items-center gap-2"
                      >
                        <div className="flex size-4 items-center justify-center rounded-sm border border-input">
                          {isSelected ? <Check className="size-3" /> : null}
                        </div>
                        <span className="flex-1 truncate font-mono text-xs">{opt.tool_name}</span>
                        {opt.otherOwners.length > 0 ? (
                          <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] text-amber-900">
                            also: {opt.otherOwners.join(', ')}
                          </span>
                        ) : null}
                        {opt.description ? (
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
                              {opt.description}
                            </TooltipContent>
                          </Tooltip>
                        ) : null}
                      </CommandItem>
                    );
                  })}
                </CommandGroup>
              ))}
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>

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
