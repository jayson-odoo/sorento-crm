'use client';

import { useEffect, useMemo, useState } from 'react';
import { ShieldCheck, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import {
  SearchableMultiSelect,
  type SearchableMultiSelectOption,
} from '@/components/common/SearchableMultiSelect';
import { useAgentFieldAccess, useSetAgentFieldAccess } from '../hooks/useAccessAgents';
import type { AgentFieldAccessRow } from '../services/accessAgentService';

interface Props {
  agentId: string;
}

/**
 * Which fields this agent may reveal.
 *
 * Holding an agent is permission to ask the QUESTION; this decides what the answer
 * may contain. Everything here is denied until selected, so a newly added sensitive
 * column is invisible to the contacts already holding the agent rather than
 * exposed to all of them on deploy day.
 *
 * A multi-select rather than a checkbox grid: an agent can own 20+ fields, and a
 * grid that tall pushed the rest of the page below the fold for a card that is
 * usually only read, not edited.
 */
export default function AgentFieldAccessCard({ agentId }: Props) {
  const { data, isLoading, isError } = useAgentFieldAccess(agentId);
  const setFieldAccess = useSetAgentFieldAccess();

  // Local selection so the whole list can be reviewed before committing - saving on
  // every click makes "allow these four" four audit entries and four chances to
  // half-apply.
  const [draft, setDraft] = useState<string[]>([]);

  const rows: AgentFieldAccessRow[] = useMemo(() => data?.fields ?? [], [data]);

  const serverAllowed = useMemo(
    () => rows.filter((f) => f.is_allowed).map((f) => `${f.resource}.${f.field_key}`),
    [rows],
  );

  useEffect(() => setDraft(serverAllowed), [serverAllowed]);

  const options: SearchableMultiSelectOption[] = useMemo(
    () =>
      rows.map((f) => ({
        value: `${f.resource}.${f.field_key}`,
        label: f.label,
        // The field key, because it is what the answer side speaks: the MCP render
        // envelope keys every field on it and `field_access.denied[].field` names
        // it. The label is admin-facing display text and does not match the
        // customer-facing one word for word, so the key is the thing to tie a
        // decision here back to what a contact does or does not get told.
        description: f.field_key,
        searchText: `${f.label} ${f.field_key} ${f.resource}`,
      })),
    [rows],
  );

  // Both directions: a field ticked on and a field ticked off are equally a change,
  // and only the changed ones are sent - two admins editing different rows must not
  // revoke each other.
  const changed = useMemo(() => {
    const before = new Set(serverAllowed);
    const after = new Set(draft);
    return rows
      .map((f) => `${f.resource}.${f.field_key}`)
      .filter((key) => before.has(key) !== after.has(key));
  }, [rows, serverAllowed, draft]);

  const save = () => {
    const selected = new Set(draft);
    const fields = changed.map((key) => {
      const [resource, ...rest] = key.split('.');
      return { resource, field_key: rest.join('.'), is_allowed: selected.has(key) };
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
            Holding this agent lets a contact ask the question. This list decides what
            the answer may contain. Anything not selected is left out of the reply entirely.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="secondary">
            {draft.length} of {rows.length} allowed
          </Badge>
          <Button size="sm" onClick={save} disabled={!changed.length || setFieldAccess.isPending}>
            {setFieldAccess.isPending ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              `Save${changed.length ? ` (${changed.length})` : ''}`
            )}
          </Button>
        </div>
      </CardHeader>

      <CardContent>
        {isLoading ? (
          <Skeleton className="h-9 w-full" />
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
          <SearchableMultiSelect
            value={draft}
            onChange={setDraft}
            options={options}
            placeholder="No fields allowed - the answer carries none of them"
            emptyMessage="No matching field."
          />
        )}
      </CardContent>
    </Card>
  );
}
