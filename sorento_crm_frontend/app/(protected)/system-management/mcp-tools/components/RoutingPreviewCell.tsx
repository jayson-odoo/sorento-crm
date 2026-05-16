'use client';

import * as React from 'react';
import { useMcpToolRouting } from '../hooks/useMcpAdmin';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Badge } from '@/components/ui/badge';

interface Props {
  toolName: string;
}

export function RoutingPreviewCell({ toolName }: Props) {
  const [open, setOpen] = React.useState(false);
  const { data, isLoading } = useMcpToolRouting(toolName, open);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="text-left text-sm underline-offset-2 hover:underline focus:outline-none"
        >
          {open && isLoading ? (
            <span className="text-muted-foreground">Loading...</span>
          ) : data?.primary ? (
            <span>
              {data.primary.team_name}
              {data.primary.tier != null ? (
                <span className="ml-1 text-xs text-muted-foreground">(tier {data.primary.tier})</span>
              ) : null}
            </span>
          ) : open ? (
            <span className="text-muted-foreground">No routing</span>
          ) : (
            <span className="text-muted-foreground">View</span>
          )}
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-[360px]" align="start">
        <div className="space-y-2">
          <div className="text-xs font-semibold uppercase text-muted-foreground">
            Escalation chain for <span className="font-mono">{toolName}</span>
          </div>
          {isLoading ? (
            <div className="text-sm text-muted-foreground">Loading…</div>
          ) : !data || data.entries.length === 0 ? (
            <div className="text-sm text-muted-foreground">
              No teams linked. Configure via <code>User Management → Access Agents</code> by
              assigning teams (with tier) to the agents that own this tool.
            </div>
          ) : (
            <ol className="space-y-1.5">
              {data.entries.map((e, idx) => (
                <li key={`${e.team_code}-${e.agent_code}-${idx}`} className="flex items-center gap-2 text-sm">
                  {e.tier != null ? (
                    <Badge variant="outline" className="font-mono text-xs">
                      T{e.tier}
                    </Badge>
                  ) : (
                    <Badge variant="outline" className="font-mono text-xs text-muted-foreground">
                      —
                    </Badge>
                  )}
                  <span className="font-medium">{e.team_name}</span>
                  <span className="text-muted-foreground">→</span>
                  <span className="text-xs">{e.agent_name}</span>
                </li>
              ))}
            </ol>
          )}
          <div className="pt-2 text-xs text-muted-foreground">
            First row = primary, sent as <code>suggested_escalation</code> on empty results.
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}
