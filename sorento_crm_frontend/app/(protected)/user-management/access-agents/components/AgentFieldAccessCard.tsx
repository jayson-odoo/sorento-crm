'use client';

import { useEffect, useMemo, useState } from 'react';
import { ShieldCheck, Loader2, UserMinus, UserCheck } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { Skeleton } from '@/components/ui/skeleton';
import { useAgentFieldAccess, useSetAgentFieldAccess } from '../hooks/useAccessAgents';
import type { AgentFieldAccessRow } from '../services/accessAgentService';

interface Props {
  agentId: string;
}

/**
 * Which fields this agent may reveal.
 *
 * Holding an agent is permission to ask the QUESTION; this decides what the answer
 * may contain. Everything here is denied until ticked, so a newly added sensitive
 * column is invisible to the contacts already holding the agent rather than
 * exposed to all of them on deploy day.
 */
export default function AgentFieldAccessCard({ agentId }: Props) {
  const { data, isLoading, isError } = useAgentFieldAccess(agentId);
  const setFieldAccess = useSetAgentFieldAccess();

  // Local ticks so the whole list can be reviewed before committing - a checkbox
  // that saves on every click makes "allow these four" four audit entries and
  // four chances to half-apply.
  const [draft, setDraft] = useState<Record<string, boolean>>({});

  const serverState = useMemo(() => {
    const map: Record<string, boolean> = {};
    for (const f of data?.fields ?? []) map[`${f.resource}.${f.field_key}`] = f.is_allowed;
    return map;
  }, [data]);

  useEffect(() => setDraft(serverState), [serverState]);

  const dirty = useMemo(
    () => Object.keys(serverState).filter((k) => draft[k] !== serverState[k]),
    [draft, serverState],
  );

  const rows: AgentFieldAccessRow[] = data?.fields ?? [];
  const allowedCount = Object.values(draft).filter(Boolean).length;

  const save = () => {
    const fields = dirty.map((key) => {
      const [resource, ...rest] = key.split('.');
      return { resource, field_key: rest.join('.'), is_allowed: draft[key] };
    });
    setFieldAccess.mutate({ agentId, fields });
  };

  return (
    <Card>
      <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <CardTitle className="flex items-center gap-2">
            <ShieldCheck className="size-4 shrink-0" />
            <span className="break-words">Fields this agent may reveal</span>
          </CardTitle>
          <p className="mt-1 text-sm text-muted-foreground">
            Holding this agent lets a contact ask the question. These ticks decide what
            the answer may contain. Anything unticked is left out of the reply entirely.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="secondary">
            {allowedCount} of {rows.length} allowed
          </Badge>
          <Button size="sm" onClick={save} disabled={!dirty.length || setFieldAccess.isPending}>
            {setFieldAccess.isPending ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              `Save${dirty.length ? ` (${dirty.length})` : ''}`
            )}
          </Button>
        </div>
      </CardHeader>

      <CardContent>
        {isLoading ? (
          <div className="grid gap-2 sm:grid-cols-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-9 w-full" />
            ))}
          </div>
        ) : isError ? (
          <p className="text-sm text-destructive">
            Could not load the field list. Reload the page to try again.
          </p>
        ) : rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            This agent owns no restricted fields. Everything it can reach is already
            visible to anyone holding it.
          </p>
        ) : (
          <div className="grid gap-1 sm:grid-cols-2">
            {rows.map((f) => {
              const key = `${f.resource}.${f.field_key}`;
              return (
                <label
                  key={key}
                  className="flex min-w-0 cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 hover:bg-muted/60"
                >
                  <Checkbox
                    checked={!!draft[key]}
                    onCheckedChange={(checked) =>
                      setDraft((prev) => ({ ...prev, [key]: checked === true }))
                    }
                  />
                  <span className="truncate text-sm" title={`${f.label} (${f.field_key})`}>
                    {f.label}
                  </span>
                </label>
              );
            })}
          </div>
        )}

        {/* Per-contact exceptions. Rendered whenever any exist, because they are the
            answer to "why does that one dealer see something different" - without
            them the ticks above look like they tell the whole story. */}
        {(data?.overrides?.length ?? 0) > 0 && (
          <div className="mt-4 border-t pt-4">
            <p className="mb-2 text-sm font-medium">Per-contact exceptions</p>
            <p className="mb-3 text-sm text-muted-foreground">
              These contacts do not follow the ticks above. Edit them on the contact&apos;s
              own page.
            </p>
            <ul className="flex flex-col gap-1">
              {(data?.overrides ?? []).map((o) => (
                <li
                  key={`${o.contact_id}.${o.resource}.${o.field_key}`}
                  className="flex min-w-0 items-center gap-2 text-sm"
                >
                  {o.is_allowed ? (
                    <UserCheck className="size-4 shrink-0 text-emerald-600" />
                  ) : (
                    <UserMinus className="size-4 shrink-0 text-destructive" />
                  )}
                  <span className="truncate">
                    <span className="font-medium">{o.contact_name || 'Unnamed contact'}</span>
                    {o.is_allowed ? ' may see ' : ' may not see '}
                    {o.label}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
