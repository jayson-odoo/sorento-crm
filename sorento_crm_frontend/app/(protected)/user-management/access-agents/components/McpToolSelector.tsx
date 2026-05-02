'use client';

import * as React from 'react';
import {
  SearchableMultiSelect,
  SearchableMultiSelectOption,
} from '@/components/common/SearchableMultiSelect';
import { useMcpToolsForPicker } from '../hooks/useAccessAgents';

export interface McpToolSelectorProps {
  /** Currently selected tool ids. */
  value: string[];
  onChange: (next: string[]) => void;
  /** Agent currently being edited; tools already linked to OTHER agents are
   *  badged with the list of co-owners (many-to-many — adding does NOT remove
   *  other agents). */
  currentAgentId?: string;
  disabled?: boolean;
}

export function McpToolSelector({
  value,
  onChange,
  currentAgentId,
  disabled,
}: McpToolSelectorProps) {
  const { data, isLoading } = useMcpToolsForPicker();
  const rows = data ?? [];

  const options: SearchableMultiSelectOption[] = React.useMemo(() => {
    return rows.map((r) => {
      const otherOwners = (r.current_agent_names ?? []).filter((_, idx) => {
        const ids = r.current_agent_ids ?? [];
        return ids[idx] !== currentAgentId;
      });
      return {
        value: r.id,
        label: r.tool_name,
        group: r.module_key || 'Unbound',
        searchText: `${r.tool_name} ${r.module_key} ${r.description ?? ''}`,
        description: r.description ?? undefined,
        badgeText:
          otherOwners.length > 0
            ? `also linked to ${otherOwners.join(', ')}`
            : undefined,
      };
    });
  }, [rows, currentAgentId]);

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
    <SearchableMultiSelect
      value={value}
      onChange={onChange}
      options={options}
      placeholder="Select MCP tools..."
      emptyMessage="No MCP tools match."
      disabled={disabled}
    />
  );
}
