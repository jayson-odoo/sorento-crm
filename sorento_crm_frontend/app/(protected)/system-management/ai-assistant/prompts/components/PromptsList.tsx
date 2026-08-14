'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { ChevronRight, Loader2 } from 'lucide-react';
import { useHasPermission } from '@/hooks/usePermissions';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { usePromptKeys } from '../../hooks/useAIAssistantPrompts';
import type { PromptKeySummary } from '../../services/aiPromptsService';

const VIEW_PERMISSION = 'system.ai_assistant_settings.view';

function formatDate(d: string | null): string {
  if (!d) return '—';
  try {
    return new Date(d).toLocaleString();
  } catch {
    return d;
  }
}

export function PromptsList() {
  const hasPermission = useHasPermission(VIEW_PERMISSION);
  const { data, isLoading, isError, error } = usePromptKeys();
  const [showInactive, setShowInactive] = useState(false);

  const { active, dormant } = useMemo(() => {
    const rows = data || [];
    return {
      active: rows.filter((r) => r.active),
      dormant: rows.filter((r) => !r.active),
    };
  }, [data]);

  if (!hasPermission) {
    return (
      <div className="rounded-md border p-6 text-sm text-muted-foreground">
        Forbidden — you don&apos;t have permission to view AI assistant prompts.
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-muted-foreground">
        <Loader2 className="size-4 animate-spin" /> Loading prompts…
      </div>
    );
  }
  if (isError) {
    return <p className="text-sm text-destructive">{(error as Error)?.message || 'Failed to load prompts'}</p>;
  }
  if ((data || []).length === 0) {
    return <p className="text-sm text-muted-foreground">No prompt keys registered yet.</p>;
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Every prompt the assistant uses is versioned here. Edit → save a new immutable version → publish to move
        the live <span className="font-medium">production</span> label. No redeploy needed.
      </p>

      <PromptTable rows={active} />

      <label className="flex items-center gap-2 text-sm" data-testid="show-inactive-toggle">
        <Checkbox checked={showInactive} onCheckedChange={(c) => setShowInactive(c === true)} />
        Show inactive prompts ({dormant.length})
      </label>

      {showInactive ? <PromptTable rows={dormant} dormant /> : null}
    </div>
  );
}

function PromptTable({ rows, dormant = false }: { rows: PromptKeySummary[]; dormant?: boolean }) {
  if (rows.length === 0) {
    return <p className="text-sm text-muted-foreground">None.</p>;
  }
  return (
    <Card>
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid={dormant ? 'dormant-prompts-table' : 'active-prompts-table'}>
            <thead>
              <tr className="border-b text-xs text-muted-foreground">
                <th className="p-3 text-left font-medium">Prompt</th>
                <th className="p-3 text-left font-medium">Role</th>
                <th className="p-3 text-left font-medium">Runs on</th>
                <th className="p-3 text-right font-medium">Production</th>
                <th className="p-3 text-right font-medium">Latest</th>
                <th className="p-3 text-left font-medium">Last edited</th>
                <th className="w-8 p-3" />
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.name} className="border-b last:border-0 hover:bg-muted/40">
                  <td className="p-3">
                    <Link
                      href={`/system-management/ai-assistant/prompts/${r.name}`}
                      className="flex items-center gap-2 font-mono font-medium hover:underline"
                      data-testid={`prompt-link-${r.name}`}
                    >
                      {r.name}
                      {dormant ? (
                        <Badge variant="warning" className="text-[10px]">
                          Dormant · {r.activates_in}
                        </Badge>
                      ) : null}
                    </Link>
                  </td>
                  <td className="max-w-[280px] p-3 text-muted-foreground">
                    <span className="line-clamp-2" title={r.role}>
                      {r.role}
                    </span>
                  </td>
                  <td className="p-3 text-xs">
                    {r.model ? (
                      <span className="font-mono">{r.model}</span>
                    ) : (
                      <span className="text-muted-foreground">Default model</span>
                    )}
                  </td>
                  <td className="p-3 text-right tabular-nums">
                    {r.production_version != null ? `v${r.production_version}` : '—'}
                  </td>
                  <td className="p-3 text-right tabular-nums text-muted-foreground">
                    {r.latest_version != null ? `v${r.latest_version}` : '—'}
                  </td>
                  <td className="p-3 text-xs text-muted-foreground">
                    {formatDate(r.updated_at)}
                    {r.updated_by_name ? ` · ${r.updated_by_name}` : ''}
                  </td>
                  <td className="p-3 text-right">
                    <Link
                      href={`/system-management/ai-assistant/prompts/${r.name}`}
                      aria-label={`Open ${r.name}`}
                    >
                      <ChevronRight className="size-4 text-muted-foreground" />
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
